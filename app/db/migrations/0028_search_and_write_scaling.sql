-- Indexes and storage settings for the queries that grow with the store, not with the page size.

-- The audit page lists every distinct action on each search. Without an index that is a full heap
-- scan of the whole log; with one PostgreSQL reads the much smaller index instead.
CREATE INDEX IF NOT EXISTS audit_logs_action ON audit_logs(action);

-- Console search uses ILIKE '%term%', which no ordinary B-tree can serve. Trigram indexes do, but
-- pg_trgm needs an extension the database role may not be allowed to create. Failing to install it
-- must not fail the release: searches then work exactly as before, only without the index.
-- An extension belongs to the database, not to a schema, so CREATE EXTENSION IF NOT EXISTS does
-- nothing when pg_trgm already lives in a schema outside this connection's search_path. The operator
-- class is therefore looked up and named explicitly rather than trusted to resolve.
DO $$
DECLARE ext_schema text;
BEGIN
    CREATE EXTENSION IF NOT EXISTS pg_trgm;
    SELECT n.nspname INTO STRICT ext_schema
    FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace WHERE e.extname = 'pg_trgm';
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS orders_title_search ON orders USING gin (product_title %I.gin_trgm_ops)', ext_schema);
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS users_username_search ON users USING gin (username %I.gin_trgm_ops)', ext_schema);
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS audit_logs_details_search ON audit_logs USING gin (details %I.gin_trgm_ops)', ext_schema);
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Trigram search indexes skipped (%); admin search keeps its existing plan.', SQLERRM;
END $$;

-- These four tables are updated far more often than they are inserted into: a rate-limit row per
-- API request, a conversation row per bot tap, an inbox row per Telegram update. Leaving free space
-- in each page lets PostgreSQL update a row in place (HOT) instead of writing a new row version and
-- every index entry with it, which is what makes a small table bloat under steady traffic.
ALTER TABLE request_limits SET (fillfactor = 70);
ALTER TABLE bot_conversations SET (fillfactor = 70);
ALTER TABLE telegram_inbox SET (fillfactor = 80);
ALTER TABLE outbox SET (fillfactor = 80);

-- Autovacuum's default 20% threshold is measured against the whole table, so a large outbox or inbox
-- is cleaned far too rarely for tables whose rows all change state. Scale the threshold down.
ALTER TABLE request_limits SET (autovacuum_vacuum_scale_factor = 0.02, autovacuum_analyze_scale_factor = 0.02);
ALTER TABLE telegram_inbox SET (autovacuum_vacuum_scale_factor = 0.05);
ALTER TABLE outbox SET (autovacuum_vacuum_scale_factor = 0.05);

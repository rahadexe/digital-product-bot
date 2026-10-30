-- Migration 0058: Financial Security Hardening
-- 1. Canonical transaction ID function: strips leading 0x prefix from crypto hashes and trims whitespace.
CREATE OR REPLACE FUNCTION canonical_txid(tx TEXT) RETURNS TEXT AS $$
BEGIN
    RETURN regexp_replace(lower(btrim(COALESCE(tx, ''))), '^0x', '');
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- 2. Drop old index and recreate canonical unique index.
-- Excludes rejected deposits so mistyped or cancelled deposits do not permanently lock a transaction ID,
-- while strictly enforcing that two pending or approved deposits can never share a transaction ID.
DROP INDEX IF EXISTS deposit_transaction_unique;
CREATE UNIQUE INDEX IF NOT EXISTS deposit_transaction_unique 
    ON deposits(canonical_txid(transaction_id)) 
    WHERE status IN ('pending', 'approved') AND NOT legacy_duplicate;

-- 3. Received transactions statement canonical unique index
DROP INDEX IF EXISTS idx_received_transactions_txid_unique;
CREATE UNIQUE INDEX IF NOT EXISTS idx_received_transactions_txid_unique 
    ON received_transactions (canonical_txid(transaction_id));

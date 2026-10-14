-- Advance orders sequence to at least 1000 so new orders start from #1001
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class WHERE relkind = 'S' AND relname = 'orders_id_seq') THEN
        PERFORM setval('orders_id_seq', GREATEST((SELECT COALESCE(MAX(id), 0) FROM orders), 1000));
    END IF;
END $$;

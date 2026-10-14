-- Advance the deposits identity sequence to at least 1000 so new deposits start at 1001.
DO $$
DECLARE
    sequence_name TEXT;
BEGIN
    sequence_name := pg_get_serial_sequence('deposits', 'id');
    IF sequence_name IS NOT NULL THEN
        PERFORM setval(
            sequence_name::regclass,
            GREATEST((SELECT COALESCE(MAX(id), 0) FROM deposits), 1000)
        );
    END IF;
END $$;

-- Migration 0016: Add text column to broadcasts table and auto-prune to latest 30
ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS text TEXT NOT NULL DEFAULT '';

-- Backfill existing broadcast text from outbox records
UPDATE broadcasts b
SET text = COALESCE((SELECT o.text FROM outbox o WHERE o.broadcast_id = b.id LIMIT 1), '')
WHERE b.text = '';

-- Keep only the latest 30 broadcasts (cascades to outbox via foreign key)
DELETE FROM broadcasts
WHERE id NOT IN (
    SELECT id FROM broadcasts ORDER BY id DESC LIMIT 30
);

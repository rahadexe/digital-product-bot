-- Repair the duplicate 0008 version: the migrator keys applied files by filename stem,
-- so 0008_stock_expiry.sql can be skipped when the other 0008 migration runs first.
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_inventory_items_product_expiry
    ON inventory_items (product_id, status, expires_at);

-- Add expires_at to inventory_items for stock auto-expiry
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_inventory_items_product_expiry
ON inventory_items (product_id, status, expires_at);

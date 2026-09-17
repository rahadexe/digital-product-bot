-- Orders that are paid but not yet delivered, where each delivery came from, and stock that can be
-- sold to more than one customer (one account with seven seats).

-- 'waiting': the customer has paid and the item is still to be sent (the supplier had no balance or failed).
ALTER TABLE orders ADD COLUMN IF NOT EXISTS fulfillment TEXT NOT NULL DEFAULT 'delivered';
ALTER TABLE orders ADD CONSTRAINT orders_fulfillment_check CHECK (fulfillment IN ('delivered', 'waiting'));
-- Where the delivered item came from: own stock, the supplier, typed by the admin, or unknown (older orders).
ALTER TABLE orders ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'legacy';
ALTER TABLE orders ADD CONSTRAINT orders_source_check CHECK (source IN ('stock', 'supplier', 'manual', 'legacy'));
ALTER TABLE orders ADD COLUMN IF NOT EXISTS inventory_item_id BIGINT REFERENCES inventory_items(id) ON DELETE SET NULL;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS fulfilled_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS orders_waiting ON orders(id) WHERE fulfillment = 'waiting' AND status = 'completed';
CREATE INDEX IF NOT EXISTS orders_inventory_item ON orders(inventory_item_id, tg_user_id);

UPDATE orders o SET inventory_item_id = i.id, source = 'stock'
FROM inventory_items i WHERE i.order_id = o.id AND o.inventory_item_id IS NULL;
UPDATE orders o SET source = 'supplier'
FROM supplier_purchase_attempts a WHERE a.order_id = o.id AND o.source = 'legacy';
UPDATE orders SET fulfilled_at = created_at WHERE fulfilled_at IS NULL;

-- A stock item can go to max_uses customers; uses counts how many it has gone to.
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS max_uses INTEGER NOT NULL DEFAULT 1;
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS uses INTEGER NOT NULL DEFAULT 0;
ALTER TABLE inventory_items ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ;
UPDATE inventory_items SET uses = 1, last_used_at = sold_at WHERE status = 'sold' AND uses = 0;
ALTER TABLE inventory_items ADD CONSTRAINT inventory_items_uses_check
    CHECK (max_uses BETWEEN 1 AND 1000 AND uses >= 0 AND uses <= max_uses);
CREATE INDEX IF NOT EXISTS inventory_items_next_seat ON inventory_items(product_id, uses, last_used_at, id) WHERE status = 'available';

-- A notice about an order that is not its receipt ("received, being prepared"), so it can be shown with the order.
ALTER TABLE outbox ADD COLUMN IF NOT EXISTS about_order_id BIGINT;
CREATE INDEX IF NOT EXISTS outbox_about_order ON outbox(about_order_id) WHERE about_order_id IS NOT NULL;

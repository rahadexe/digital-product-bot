-- Performance indexes for foreign keys, common filters, and scalability.
-- Missing FK indexes cause sequential scans when the parent is deleted or joined.

-- outbox(broadcast_id): CASCADE deletes from broadcasts, status queries
CREATE INDEX IF NOT EXISTS idx_outbox_broadcast_id ON outbox(broadcast_id) WHERE broadcast_id IS NOT NULL;

-- orders foreign keys and common filters
CREATE INDEX IF NOT EXISTS idx_orders_product_id ON orders(product_id);
CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);

-- Composite index for the claim_seats subquery: avoids per-row scans during stock allocation sorting
CREATE INDEX IF NOT EXISTS idx_orders_inventory_user ON orders(inventory_item_id, tg_user_id);

-- deposits foreign keys
CREATE INDEX IF NOT EXISTS idx_deposits_user_id ON deposits(user_id);
CREATE INDEX IF NOT EXISTS idx_deposits_method_id ON deposits(method_id);

-- inventory_items(order_id): FK lookups when orders are referenced
CREATE INDEX IF NOT EXISTS idx_inventory_items_order_id ON inventory_items(order_id) WHERE order_id IS NOT NULL;

-- Safety: prevent negative balance at the database level
ALTER TABLE users ADD CONSTRAINT users_balance_nonneg CHECK (balance >= 0);

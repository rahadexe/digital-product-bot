-- Migration 0041: Restock notification subscriptions
CREATE TABLE IF NOT EXISTS restock_notifications (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    tg_user_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(product_id, tg_user_id)
);
CREATE INDEX IF NOT EXISTS idx_restock_notifications_product_id ON restock_notifications(product_id);

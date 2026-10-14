-- Persist before calling a supplier, independently of the wallet transaction.
-- No foreign keys: this journal must not wait for uncommitted order/wallet rows.
CREATE TABLE supplier_order_attempts (
    request_key TEXT PRIMARY KEY,
    supplier_code TEXT NOT NULL,
    tg_user_id BIGINT NOT NULL,
    local_product_id BIGINT NOT NULL,
    customer_request_id TEXT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    status TEXT NOT NULL CHECK (status IN ('sending', 'accepted', 'refused', 'unknown')),
    response JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX supplier_order_attempts_unresolved
    ON supplier_order_attempts(updated_at) WHERE status IN ('sending', 'unknown');

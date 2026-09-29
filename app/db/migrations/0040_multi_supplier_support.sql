-- Migration 0040: Multi-supplier support and graceful fallback
ALTER TABLE products ADD COLUMN IF NOT EXISTS supplier_code VARCHAR(64) DEFAULT 'digital_mart';
CREATE INDEX IF NOT EXISTS idx_products_supplier ON products(supplier_code, upstream_product_id) WHERE upstream_product_id IS NOT NULL;

ALTER TABLE orders ADD COLUMN IF NOT EXISTS supplier_code VARCHAR(64);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS supplier_order_id VARCHAR(128);
ALTER TABLE orders ADD COLUMN IF NOT EXISTS supplier_error TEXT;

DO $$
BEGIN
    ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_source_check;
    ALTER TABLE orders ADD CONSTRAINT orders_source_check 
        CHECK (source IN ('stock', 'supplier', 'upstream_reseller', 'manual', 'legacy', 'supplier_pending', 'upstream_fallback'));
EXCEPTION
    WHEN OTHERS THEN NULL;
END $$;

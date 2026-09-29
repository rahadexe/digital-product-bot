-- Migration 0037: Add upstream_product_id to products for external reseller integration
ALTER TABLE products ADD COLUMN IF NOT EXISTS upstream_product_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_products_upstream_id ON products(upstream_product_id) WHERE upstream_product_id IS NOT NULL;

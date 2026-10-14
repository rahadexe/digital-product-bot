-- Add is_pinned to products table to allow pinning products to top within category / store
ALTER TABLE products ADD COLUMN IF NOT EXISTS is_pinned INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_products_pinned_sort ON products(is_pinned, category_id, sort_order, id);

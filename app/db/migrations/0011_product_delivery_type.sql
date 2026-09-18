-- Add delivery_type to products table: 'stock' (instant auto delivery) or 'manual' (admin fulfills)
ALTER TABLE products ADD COLUMN IF NOT EXISTS delivery_type TEXT NOT NULL DEFAULT 'stock';
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'products_delivery_type_check'
    ) THEN
        ALTER TABLE products ADD CONSTRAINT products_delivery_type_check CHECK (delivery_type IN ('stock', 'manual'));
    END IF;
END $$;

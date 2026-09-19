-- Add reseller_price column to products table for reseller tier pricing.
ALTER TABLE products ADD COLUMN IF NOT EXISTS reseller_price NUMERIC(18,4) DEFAULT NULL;

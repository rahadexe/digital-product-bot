-- Migration 0039: Add upstream_devices and upstream_share_hours to products for multi-device seat sharing
ALTER TABLE products ADD COLUMN IF NOT EXISTS upstream_devices INTEGER NOT NULL DEFAULT 1;
ALTER TABLE products ADD COLUMN IF NOT EXISTS upstream_share_hours INTEGER NOT NULL DEFAULT 24;

COMMENT ON COLUMN products.upstream_devices IS 'Number of customer seats/devices a single supplier account can serve (1 = private/single, >1 = shared)';
COMMENT ON COLUMN products.upstream_share_hours IS 'Maximum window in hours to sell remaining seats from a supplier account before it expires';

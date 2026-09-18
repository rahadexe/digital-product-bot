-- Migration 0015: Add has_validity_filter to categories table
ALTER TABLE categories ADD COLUMN IF NOT EXISTS has_validity_filter INTEGER NOT NULL DEFAULT 0;

-- Enable for VPN category
UPDATE categories SET has_validity_filter = 1 WHERE id = 1 OR LOWER(name) LIKE '%vpn%';

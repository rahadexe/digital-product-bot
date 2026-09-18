-- Add is_pinned and custom_emoji_id to categories table
ALTER TABLE categories ADD COLUMN IF NOT EXISTS is_pinned INTEGER NOT NULL DEFAULT 0;
ALTER TABLE categories ADD COLUMN IF NOT EXISTS custom_emoji_id TEXT;
CREATE INDEX IF NOT EXISTS idx_categories_pinned ON categories(is_pinned, is_active, sort_order);

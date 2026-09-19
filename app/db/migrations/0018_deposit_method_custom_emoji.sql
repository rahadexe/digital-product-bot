-- Add custom_emoji_id to deposit_methods table
ALTER TABLE deposit_methods ADD COLUMN IF NOT EXISTS custom_emoji_id TEXT;

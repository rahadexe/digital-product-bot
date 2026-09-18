-- Add custom_emoji_id to products for Telegram Bot API 9.4+ custom emoji support
ALTER TABLE products ADD COLUMN IF NOT EXISTS custom_emoji_id TEXT;

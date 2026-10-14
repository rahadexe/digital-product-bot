-- Support custom customer input upon purchase (e.g., Gmail for Gemini/Canva, username, custom domain)
ALTER TABLE products ADD COLUMN IF NOT EXISTS requires_customer_input BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE products ADD COLUMN IF NOT EXISTS customer_input_prompt TEXT NOT NULL DEFAULT '';
ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_input TEXT NOT NULL DEFAULT '';

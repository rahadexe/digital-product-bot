-- Migration 0057: Add currency preference column to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS currency VARCHAR(10) DEFAULT 'BDT';

UPDATE users
   SET currency = CASE
       WHEN lower(COALESCE(language, '')) = 'en' THEN 'USD'
       ELSE 'BDT'
   END
 WHERE currency IS NULL OR currency = '';

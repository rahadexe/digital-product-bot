ALTER TABLE categories ALTER COLUMN icon SET DEFAULT '';
ALTER TABLE products ALTER COLUMN icon SET DEFAULT '';

UPDATE categories
SET icon = ''
WHERE icon = '📦'
   OR (COALESCE(custom_emoji_id, '') <> '' AND COALESCE(icon, '') <> '');

UPDATE products
SET icon = ''
WHERE icon = '⚡'
   OR (COALESCE(custom_emoji_id, '') <> '' AND COALESCE(icon, '') <> '');

ALTER TABLE categories
    ADD CONSTRAINT categories_single_icon_check
    CHECK (COALESCE(icon, '') = '' OR COALESCE(custom_emoji_id, '') = '');

ALTER TABLE products
    ADD CONSTRAINT products_single_icon_check
    CHECK (COALESCE(icon, '') = '' OR COALESCE(custom_emoji_id, '') = '');

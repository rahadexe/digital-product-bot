-- Supplier integration is retired. Preserve historical attempts as audit records.
INSERT INTO audit_logs(action, details)
SELECT 'supplier_history_archived', row_to_json(a)::text FROM supplier_purchase_attempts a;
DROP TABLE supplier_purchase_attempts;
ALTER TABLE products DROP COLUMN supplier_product_id;
ALTER TABLE products DROP COLUMN supplier_price;
ALTER TABLE products DROP COLUMN supplier_stock;
DROP TABLE media_assets;
DROP TABLE home_banners;
DROP TABLE bot_welcome_banners;
DELETE FROM bot_settings WHERE key IN ('notice_banner','supplier_api_url','supplier_api_key','referral_bonus_percent','custom_emojis');
INSERT INTO bot_settings(key,value) VALUES ('currency','BDT'),('currency_symbol','৳'),('zinipay_rate','1')
ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value;

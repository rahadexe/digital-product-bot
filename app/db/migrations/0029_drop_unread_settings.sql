-- store_tagline and store_description were written by the console and read by
-- nothing: the Mini App that showed them was removed, and no bot or API path
-- ever looked them up. Dropping the rows keeps bot_settings to what the shop
-- actually uses; the keys are gone from SPECS, so a write would now be refused.
DELETE FROM bot_settings WHERE key IN ('store_tagline', 'store_description');

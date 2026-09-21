-- The guide describes this bot's own buttons, so it is written in the handler
-- rather than stored: an operator editing it could only make it disagree with
-- the keyboard the customer is looking at. The key is gone from SPECS, so a
-- write would now be refused; this drops whatever was stored under it.
DELETE FROM bot_settings WHERE key = 'guide_text';

UPDATE bot_settings
SET value = ''
WHERE key = 'validity_presets'
  AND value = '3 Days, 7 Days, 14 Days, 30 Days, 90 Days, 1 Year';

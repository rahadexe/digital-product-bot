-- Customer copy is English; retain the Bangladesh marker only for BDT price equivalents.
ALTER TABLE users ALTER COLUMN language SET DEFAULT 'en-BD';

UPDATE users
SET language = 'en-BD'
WHERE lower(language) = 'bn';

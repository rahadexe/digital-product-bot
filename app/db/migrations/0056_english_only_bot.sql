ALTER TABLE users ALTER COLUMN language SET DEFAULT 'en';

UPDATE users
SET language = 'en'
WHERE language IS DISTINCT FROM 'en';

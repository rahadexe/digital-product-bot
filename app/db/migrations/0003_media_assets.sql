-- Images uploaded in the admin console, kept in the database so they survive container redeploys.
-- Today only the Mini App home banner; the key list grows with each new image slot.
CREATE TABLE IF NOT EXISTS media_assets (
    key TEXT PRIMARY KEY CHECK (key IN ('home_banner')),
    content_type TEXT NOT NULL CHECK (content_type IN ('image/jpeg', 'image/png', 'image/webp')),
    data BYTEA NOT NULL CHECK (octet_length(data) BETWEEN 1 AND 921600),
    width INTEGER NOT NULL CHECK (width > 0),
    height INTEGER NOT NULL CHECK (height > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Bot welcome banner uploaded in admin settings
CREATE TABLE IF NOT EXISTS bot_welcome_banners (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    content_type TEXT NOT NULL CHECK (content_type IN ('image/jpeg', 'image/png', 'image/webp')),
    data BYTEA NOT NULL CHECK (octet_length(data) BETWEEN 1 AND 5242880),
    width INTEGER NOT NULL CHECK (width > 0),
    height INTEGER NOT NULL CHECK (height > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

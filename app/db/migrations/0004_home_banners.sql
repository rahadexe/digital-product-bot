-- Several home banners, shown one after another in the Mini App. A banner uploaded before this keeps its place as the first.
CREATE TABLE IF NOT EXISTS home_banners (
    id BIGSERIAL PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    content_type TEXT NOT NULL CHECK (content_type IN ('image/jpeg', 'image/png', 'image/webp')),
    data BYTEA NOT NULL CHECK (octet_length(data) BETWEEN 1 AND 921600),
    width INTEGER NOT NULL CHECK (width > 0),
    height INTEGER NOT NULL CHECK (height > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO home_banners (position, content_type, data, width, height, created_at)
SELECT 0, content_type, data, width, height, updated_at
FROM media_assets
WHERE key = 'home_banner' AND NOT EXISTS (SELECT 1 FROM home_banners);

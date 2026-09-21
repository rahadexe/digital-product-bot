CREATE TABLE request_limits (
    key TEXT PRIMARY KEY,
    hits INTEGER NOT NULL CHECK(hits>0),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX request_limits_expiry ON request_limits(expires_at);

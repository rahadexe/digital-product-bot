-- Per-method encrypted Binance API credentials
CREATE TABLE IF NOT EXISTS binance_method_credentials (
    method_id INT PRIMARY KEY REFERENCES deposit_methods(id) ON DELETE CASCADE,
    api_key_encrypted TEXT NOT NULL,
    api_secret_encrypted TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

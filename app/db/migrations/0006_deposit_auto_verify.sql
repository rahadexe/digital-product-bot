-- Payment methods that a provider can confirm for us: a USDT method can be checked against the
-- shop's Binance deposit history, so a matching transaction ID credits the wallet without review.
ALTER TABLE deposit_methods ADD COLUMN IF NOT EXISTS auto_verify TEXT NOT NULL DEFAULT 'none';
ALTER TABLE deposit_methods ADD COLUMN IF NOT EXISTS auto_verify_network TEXT NOT NULL DEFAULT '';
ALTER TABLE deposit_methods ADD CONSTRAINT deposit_methods_auto_verify_check CHECK (auto_verify IN ('none', 'binance'));

-- The automatic check runs over pending deposits of those methods.
CREATE INDEX IF NOT EXISTS deposits_pending_review ON deposits(status, created_at) WHERE status = 'pending';

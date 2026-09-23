CREATE TABLE admin_wallet_operations (
 operation_id TEXT PRIMARY KEY,
 tg_user_id BIGINT NOT NULL,
 delta NUMERIC(20,4) NOT NULL,
 reason TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE outbox ADD COLUMN lease_token TEXT;
CREATE INDEX admin_notification_jobs_retention ON admin_notification_jobs(created_at) WHERE status='done';

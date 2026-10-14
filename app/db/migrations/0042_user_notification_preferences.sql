-- Migration 0042: User notification preferences
CREATE TABLE IF NOT EXISTS user_notification_preferences (
    tg_user_id BIGINT PRIMARY KEY,
    notify_orders BOOLEAN NOT NULL DEFAULT TRUE,
    notify_deposits BOOLEAN NOT NULL DEFAULT TRUE,
    notify_news BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Existing history is not discarded when new integrity rules are introduced.
ALTER TABLE users ADD CONSTRAINT users_referrer_fk FOREIGN KEY(referred_by) REFERENCES users(tg_user_id) NOT VALID;
ALTER TABLE referral_rewards ADD CONSTRAINT referral_rewards_referrer_fk FOREIGN KEY(referrer_tg_id) REFERENCES users(tg_user_id) NOT VALID;
ALTER TABLE referral_rewards ADD CONSTRAINT referral_rewards_referred_fk FOREIGN KEY(referred_tg_id) REFERENCES users(tg_user_id) NOT VALID;
ALTER TABLE referral_rewards ADD CONSTRAINT referral_reward_positive CHECK(amount>0) NOT VALID;
ALTER TABLE outbox ADD CONSTRAINT outbox_about_order_fk FOREIGN KEY(about_order_id) REFERENCES orders(id) NOT VALID;

CREATE FUNCTION validate_customer_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.user_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM users WHERE id=NEW.user_id AND tg_user_id=NEW.tg_user_id
    ) THEN
        RAISE foreign_key_violation USING MESSAGE='Customer ID and Telegram ID must name the same account';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER orders_customer_identity BEFORE INSERT OR UPDATE OF user_id,tg_user_id ON orders
FOR EACH ROW EXECUTE FUNCTION validate_customer_identity();
CREATE TRIGGER deposits_customer_identity BEFORE INSERT OR UPDATE OF user_id,tg_user_id ON deposits
FOR EACH ROW EXECUTE FUNCTION validate_customer_identity();
CREATE TRIGGER invoices_customer_identity BEFORE INSERT OR UPDATE OF user_id,tg_user_id ON payment_invoices
FOR EACH ROW EXECUTE FUNCTION validate_customer_identity();

CREATE INDEX verification_limits_expiry ON verification_limits(expires_at);
CREATE INDEX telegram_inbox_retention ON telegram_inbox(created_at) WHERE status='done';
CREATE INDEX bot_conversations_retention ON bot_conversations(updated_at) WHERE state IS NULL;
CREATE INDEX revoked_sessions_expiry ON revoked_admin_sessions(expires_at);
CREATE INDEX login_attempts_retention ON admin_login_attempts(attempted_at);
ALTER TABLE payment_invoices ADD COLUMN next_check_at TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE INDEX payment_invoices_schedule ON payment_invoices(next_check_at,id) WHERE status IN ('created','pending');

-- Match the priority expression used by the worker, and only index live jobs.
CREATE INDEX outbox_priority_due ON outbox(
    (CASE WHEN order_id IS NOT NULL OR about_order_id IS NOT NULL THEN 0 ELSE 1 END), id, next_attempt
) WHERE status IN ('pending','sending');

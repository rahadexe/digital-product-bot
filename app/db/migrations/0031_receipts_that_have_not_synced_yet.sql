-- A bKash or Nagad receipt reaches the gateway a little after the customer taps send: the
-- merchant SIM has to get the SMS and the gateway has to ingest it. The bot waited fifteen
-- seconds, then told the customer their transaction did not exist and charged them one of
-- three attempts for it. Such a deposit is now filed and re-checked in the background until
-- the receipt lands, which needs a state of its own.
ALTER TABLE payment_verification_attempts DROP CONSTRAINT payment_verification_attempts_status_check;
ALTER TABLE payment_verification_attempts ADD CONSTRAINT payment_verification_attempts_status_check
    CHECK (status IN ('awaiting_sms', 'reserved', 'confirming', 'confirmed', 'review', 'completed'));

CREATE INDEX payment_verification_awaiting ON payment_verification_attempts(deposit_id)
    WHERE status = 'awaiting_sms';

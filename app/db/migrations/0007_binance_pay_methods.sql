-- A payment method can also be confirmed from Binance Pay: the customer sends to the shop's Binance
-- account and names themselves by their Binance ID, which the transfer carries.
ALTER TABLE deposit_methods DROP CONSTRAINT IF EXISTS deposit_methods_auto_verify_check;
ALTER TABLE deposit_methods ADD CONSTRAINT deposit_methods_auto_verify_check
    CHECK (auto_verify IN ('none', 'binance', 'binance_pay'));

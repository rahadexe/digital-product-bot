-- Migration 0045: Allow 'zinipay' in deposit_methods.auto_verify check constraint
ALTER TABLE deposit_methods DROP CONSTRAINT IF EXISTS deposit_methods_auto_verify_check;
ALTER TABLE deposit_methods ADD CONSTRAINT deposit_methods_auto_verify_check
    CHECK (auto_verify IN ('none', 'binance', 'binance_pay', 'zinipay'));

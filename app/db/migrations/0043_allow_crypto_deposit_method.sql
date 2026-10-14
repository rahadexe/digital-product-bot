-- Allow 'crypto' in deposit_methods.account_type
ALTER TABLE deposit_methods DROP CONSTRAINT IF EXISTS deposit_methods_account_type_check;
ALTER TABLE deposit_methods ADD CONSTRAINT deposit_methods_account_type_check CHECK (account_type IN ('personal', 'agent', 'merchant', 'crypto'));

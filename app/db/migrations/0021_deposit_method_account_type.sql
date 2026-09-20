-- Add account_type to deposit_methods (personal, agent, merchant)
ALTER TABLE deposit_methods ADD COLUMN IF NOT EXISTS account_type TEXT NOT NULL DEFAULT 'personal';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'deposit_methods_account_type_check'
    ) THEN
        ALTER TABLE deposit_methods
        ADD CONSTRAINT deposit_methods_account_type_check
        CHECK (account_type IN ('personal', 'agent', 'merchant'));
    END IF;
END $$;

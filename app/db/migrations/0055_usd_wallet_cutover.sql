-- 0055: make the wallet and all catalog prices USD-canonical; retain local payment amounts.
DO $$
DECLARE
    fx NUMERIC(18,8);
BEGIN
    SELECT CASE WHEN value ~ '^[0-9]+([.][0-9]+)?$' THEN value::NUMERIC ELSE 125 END
      INTO fx FROM bot_settings WHERE key = 'usd_rate';
    IF fx IS NULL OR fx <= 0 THEN
        fx := 125;
    END IF;

    -- Preserve the customer's actual paid amount/currency before converting wallet credits.
    UPDATE deposits d
       SET pay_amount = COALESCE(
               d.pay_amount,
               CASE WHEN (m.auto_verify IN ('binance', 'binance_pay') OR m.account_type = 'crypto' OR lower(m.name) LIKE '%binance%')
                    THEN d.amount / COALESCE(NULLIF(d.rate_to_currency, 0), fx)
                    ELSE d.amount END
           ),
           paid_currency = CASE WHEN (m.auto_verify IN ('binance', 'binance_pay') OR m.account_type = 'crypto' OR lower(m.name) LIKE '%binance%')
                                THEN 'USDT' ELSE 'BDT' END
      FROM deposit_methods m
     WHERE m.id = d.method_id;

    -- Older or deleted payment methods may no longer join; retain their recorded BDT/USDT payment basis.
    UPDATE deposits
       SET pay_amount = COALESCE(pay_amount, CASE WHEN lower(method_name) LIKE '%binance%'
                                                  THEN amount / COALESCE(NULLIF(rate_to_currency, 0), fx)
                                                  ELSE amount END),
           paid_currency = CASE WHEN lower(method_name) LIKE '%binance%' THEN 'USDT' ELSE paid_currency END
     WHERE pay_amount IS NULL;

    ALTER TABLE users DISABLE TRIGGER wallet_change;
    ALTER TABLE wallet_ledger DISABLE TRIGGER wallet_ledger_immutable;

    UPDATE users SET balance = ROUND(balance / fx, 4),
                     total_spent = ROUND(total_spent / fx, 4),
                     referral_earnings = ROUND(referral_earnings / fx, 4);
    WITH converted AS (
        SELECT id, user_id, ROUND(delta / fx, 4) AS usd_delta,
               SUM(ROUND(delta / fx, 4)) OVER (PARTITION BY user_id ORDER BY id ROWS UNBOUNDED PRECEDING) AS running_balance
          FROM wallet_ledger
    )
    UPDATE wallet_ledger AS ledger
       SET delta = converted.usd_delta,
           balance_before = converted.running_balance - converted.usd_delta,
           balance_after = converted.running_balance
      FROM converted WHERE ledger.id = converted.id;

    -- Ensure every account has a USD opening entry, then explicitly ledger any sub-cent
    -- rounding difference so the final ledger balance still matches the wallet.
    INSERT INTO wallet_ledger(user_id, tg_user_id, delta, balance_before, balance_after, reason)
    SELECT u.id, u.tg_user_id, u.balance, 0, u.balance, 'currency_cutover_opening'
      FROM users u WHERE NOT EXISTS (SELECT 1 FROM wallet_ledger l WHERE l.user_id = u.id);
    WITH latest AS (
        SELECT DISTINCT ON (user_id) user_id, balance_after
          FROM wallet_ledger ORDER BY user_id, id DESC
    )
    INSERT INTO wallet_ledger(user_id, tg_user_id, delta, balance_before, balance_after, reason)
    SELECT u.id, u.tg_user_id, u.balance - latest.balance_after, latest.balance_after, u.balance,
           'currency_cutover_rounding'
      FROM users u JOIN latest ON latest.user_id = u.id
     WHERE u.balance <> latest.balance_after;

    UPDATE products SET price = GREATEST(ROUND(price / fx, 4), 0.0001),
                        reseller_price = CASE WHEN reseller_price IS NULL THEN NULL ELSE ROUND(reseller_price / fx, 4) END,
                        supplier_price = CASE WHEN supplier_price IS NULL THEN NULL ELSE ROUND(supplier_price / fx, 4) END;
    UPDATE orders SET price = ROUND(price / fx, 4),
                      unit_price = CASE WHEN unit_price IS NULL THEN NULL ELSE GREATEST(ROUND(unit_price / fx, 4), 0.0001) END,
                      referral_bonus = ROUND(referral_bonus / fx, 4);
    UPDATE deposits SET amount = GREATEST(ROUND(amount / fx, 4), 0.0001);
    UPDATE payment_invoices SET credit_amount = GREATEST(ROUND(credit_amount / fx, 4), 0.0001), rate = fx;
    UPDATE referral_rewards SET amount = ROUND(amount / fx, 4);
    UPDATE referral_recoveries SET outstanding = GREATEST(ROUND(outstanding / fx, 4), 0.0001);

    UPDATE deposit_methods SET min_deposit = CASE WHEN auto_verify = 'binance' THEN ROUND(min_deposit / fx, 4) ELSE min_deposit END,
                              rate_to_currency = CASE WHEN account_type = 'crypto' OR lower(name) LIKE '%binance%' THEN 1 ELSE fx END;

    UPDATE bot_settings SET value = 'USD' WHERE key = 'currency';
    UPDATE bot_settings SET value = '$' WHERE key = 'currency_symbol';
    UPDATE bot_settings SET value = '1' WHERE key = 'zinipay_rate';
    UPDATE bot_settings SET value = '1' WHERE key = 'binance_pay_rate';
    UPDATE bot_settings SET value = (ROUND(value::NUMERIC / fx, 4))::TEXT
     WHERE key IN ('referral_reward_amount', 'max_deposit_limit')
       AND value ~ '^[0-9]+([.][0-9]+)?$';
    INSERT INTO bot_settings (key, value) VALUES ('currency_cutover_rate', fx::TEXT)
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

    ALTER TABLE wallet_ledger ENABLE TRIGGER wallet_ledger_immutable;
    ALTER TABLE users ENABLE TRIGGER wallet_change;
END $$;
 THEN value::NUMERIC ELSE 125 END
      INTO fx FROM bot_settings WHERE key = 'usd_rate';
    IF fx IS NULL OR fx <= 0 THEN
        fx := 125;
    END IF;

    -- Preserve the customer's actual paid amount/currency before converting wallet credits.
    UPDATE deposits d
       SET pay_amount = COALESCE(
               d.pay_amount,
               CASE WHEN (m.auto_verify IN ('binance', 'binance_pay') OR m.account_type = 'crypto' OR lower(m.name) LIKE '%binance%')
                    THEN d.amount / COALESCE(NULLIF(d.rate_to_currency, 0), fx)
                    ELSE d.amount END
           ),
           paid_currency = CASE WHEN (m.auto_verify IN ('binance', 'binance_pay') OR m.account_type = 'crypto' OR lower(m.name) LIKE '%binance%')
                                THEN 'USDT' ELSE 'BDT' END
      FROM deposit_methods m
     WHERE m.id = d.method_id;

    -- Older or deleted payment methods may no longer join; retain their recorded BDT/USDT payment basis.
    UPDATE deposits
       SET pay_amount = COALESCE(pay_amount, CASE WHEN lower(method_name) LIKE '%binance%'
                                                  THEN amount / COALESCE(NULLIF(rate_to_currency, 0), fx)
                                                  ELSE amount END),
           paid_currency = CASE WHEN lower(method_name) LIKE '%binance%' THEN 'USDT' ELSE paid_currency END
     WHERE pay_amount IS NULL;

    ALTER TABLE users DISABLE TRIGGER wallet_change;
    ALTER TABLE wallet_ledger DISABLE TRIGGER wallet_ledger_immutable;

    UPDATE users SET balance = ROUND(balance / fx, 4),
                     total_spent = ROUND(total_spent / fx, 4),
                     referral_earnings = ROUND(referral_earnings / fx, 4);
    WITH converted AS (
        SELECT id, user_id, ROUND(delta / fx, 4) AS usd_delta,
               SUM(ROUND(delta / fx, 4)) OVER (PARTITION BY user_id ORDER BY id ROWS UNBOUNDED PRECEDING) AS running_balance
          FROM wallet_ledger
    )
    UPDATE wallet_ledger AS ledger
       SET delta = converted.usd_delta,
           balance_before = converted.running_balance - converted.usd_delta,
           balance_after = converted.running_balance
      FROM converted WHERE ledger.id = converted.id;

    -- Ensure every account has a USD opening entry, then explicitly ledger any sub-cent
    -- rounding difference so the final ledger balance still matches the wallet.
    INSERT INTO wallet_ledger(user_id, tg_user_id, delta, balance_before, balance_after, reason)
    SELECT u.id, u.tg_user_id, u.balance, 0, u.balance, 'currency_cutover_opening'
      FROM users u WHERE NOT EXISTS (SELECT 1 FROM wallet_ledger l WHERE l.user_id = u.id);
    WITH latest AS (
        SELECT DISTINCT ON (user_id) user_id, balance_after
          FROM wallet_ledger ORDER BY user_id, id DESC
    )
    INSERT INTO wallet_ledger(user_id, tg_user_id, delta, balance_before, balance_after, reason)
    SELECT u.id, u.tg_user_id, u.balance - latest.balance_after, latest.balance_after, u.balance,
           'currency_cutover_rounding'
      FROM users u JOIN latest ON latest.user_id = u.id
     WHERE u.balance <> latest.balance_after;

    UPDATE products SET price = GREATEST(ROUND(price / fx, 4), 0.0001),
                        reseller_price = CASE WHEN reseller_price IS NULL THEN NULL ELSE ROUND(reseller_price / fx, 4) END,
                        supplier_price = CASE WHEN supplier_price IS NULL THEN NULL ELSE ROUND(supplier_price / fx, 4) END;
    UPDATE orders SET price = ROUND(price / fx, 4),
                      unit_price = CASE WHEN unit_price IS NULL THEN NULL ELSE GREATEST(ROUND(unit_price / fx, 4), 0.0001) END,
                      referral_bonus = ROUND(referral_bonus / fx, 4);
    UPDATE deposits SET amount = GREATEST(ROUND(amount / fx, 4), 0.0001);
    UPDATE payment_invoices SET credit_amount = GREATEST(ROUND(credit_amount / fx, 4), 0.0001), rate = fx;
    UPDATE referral_rewards SET amount = ROUND(amount / fx, 4);
    UPDATE referral_recoveries SET outstanding = GREATEST(ROUND(outstanding / fx, 4), 0.0001);

    UPDATE deposit_methods SET min_deposit = CASE WHEN auto_verify = 'binance' THEN ROUND(min_deposit / fx, 4) ELSE min_deposit END,
                              rate_to_currency = CASE WHEN account_type = 'crypto' OR lower(name) LIKE '%binance%' THEN 1 ELSE fx END;

    UPDATE bot_settings SET value = 'USD' WHERE key = 'currency';
    UPDATE bot_settings SET value = '$' WHERE key = 'currency_symbol';
    UPDATE bot_settings SET value = '1' WHERE key = 'zinipay_rate';
    UPDATE bot_settings SET value = '1' WHERE key = 'binance_pay_rate';
    UPDATE bot_settings SET value = (ROUND(value::NUMERIC / fx, 4))::TEXT WHERE key IN ('referral_reward_amount', 'max_deposit_limit');
    INSERT INTO bot_settings (key, value) VALUES ('currency_cutover_rate', fx::TEXT)
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

    ALTER TABLE wallet_ledger ENABLE TRIGGER wallet_ledger_immutable;
    ALTER TABLE users ENABLE TRIGGER wallet_change;
END $$;
;
    INSERT INTO bot_settings (key, value) VALUES ('currency_cutover_rate', fx::TEXT)
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

    ALTER TABLE wallet_ledger ENABLE TRIGGER wallet_ledger_immutable;
    ALTER TABLE users ENABLE TRIGGER wallet_change;
END $$;
 THEN value::NUMERIC ELSE 125 END
      INTO fx FROM bot_settings WHERE key = 'usd_rate';
    IF fx IS NULL OR fx <= 0 THEN
        fx := 125;
    END IF;

    -- Preserve the customer's actual paid amount/currency before converting wallet credits.
    UPDATE deposits d
       SET pay_amount = COALESCE(
               d.pay_amount,
               CASE WHEN (m.auto_verify IN ('binance', 'binance_pay') OR m.account_type = 'crypto' OR lower(m.name) LIKE '%binance%')
                    THEN d.amount / COALESCE(NULLIF(d.rate_to_currency, 0), fx)
                    ELSE d.amount END
           ),
           paid_currency = CASE WHEN (m.auto_verify IN ('binance', 'binance_pay') OR m.account_type = 'crypto' OR lower(m.name) LIKE '%binance%')
                                THEN 'USDT' ELSE 'BDT' END
      FROM deposit_methods m
     WHERE m.id = d.method_id;

    -- Older or deleted payment methods may no longer join; retain their recorded BDT/USDT payment basis.
    UPDATE deposits
       SET pay_amount = COALESCE(pay_amount, CASE WHEN lower(method_name) LIKE '%binance%'
                                                  THEN amount / COALESCE(NULLIF(rate_to_currency, 0), fx)
                                                  ELSE amount END),
           paid_currency = CASE WHEN lower(method_name) LIKE '%binance%' THEN 'USDT' ELSE paid_currency END
     WHERE pay_amount IS NULL;

    ALTER TABLE users DISABLE TRIGGER wallet_change;
    ALTER TABLE wallet_ledger DISABLE TRIGGER wallet_ledger_immutable;

    UPDATE users SET balance = ROUND(balance / fx, 4),
                     total_spent = ROUND(total_spent / fx, 4),
                     referral_earnings = ROUND(referral_earnings / fx, 4);
    WITH converted AS (
        SELECT id, user_id, ROUND(delta / fx, 4) AS usd_delta,
               SUM(ROUND(delta / fx, 4)) OVER (PARTITION BY user_id ORDER BY id ROWS UNBOUNDED PRECEDING) AS running_balance
          FROM wallet_ledger
    )
    UPDATE wallet_ledger AS ledger
       SET delta = converted.usd_delta,
           balance_before = converted.running_balance - converted.usd_delta,
           balance_after = converted.running_balance
      FROM converted WHERE ledger.id = converted.id;

    -- Ensure every account has a USD opening entry, then explicitly ledger any sub-cent
    -- rounding difference so the final ledger balance still matches the wallet.
    INSERT INTO wallet_ledger(user_id, tg_user_id, delta, balance_before, balance_after, reason)
    SELECT u.id, u.tg_user_id, u.balance, 0, u.balance, 'currency_cutover_opening'
      FROM users u WHERE NOT EXISTS (SELECT 1 FROM wallet_ledger l WHERE l.user_id = u.id);
    WITH latest AS (
        SELECT DISTINCT ON (user_id) user_id, balance_after
          FROM wallet_ledger ORDER BY user_id, id DESC
    )
    INSERT INTO wallet_ledger(user_id, tg_user_id, delta, balance_before, balance_after, reason)
    SELECT u.id, u.tg_user_id, u.balance - latest.balance_after, latest.balance_after, u.balance,
           'currency_cutover_rounding'
      FROM users u JOIN latest ON latest.user_id = u.id
     WHERE u.balance <> latest.balance_after;

    UPDATE products SET price = GREATEST(ROUND(price / fx, 4), 0.0001),
                        reseller_price = CASE WHEN reseller_price IS NULL THEN NULL ELSE ROUND(reseller_price / fx, 4) END,
                        supplier_price = CASE WHEN supplier_price IS NULL THEN NULL ELSE ROUND(supplier_price / fx, 4) END;
    UPDATE orders SET price = ROUND(price / fx, 4),
                      unit_price = CASE WHEN unit_price IS NULL THEN NULL ELSE GREATEST(ROUND(unit_price / fx, 4), 0.0001) END,
                      referral_bonus = ROUND(referral_bonus / fx, 4);
    UPDATE deposits SET amount = GREATEST(ROUND(amount / fx, 4), 0.0001);
    UPDATE payment_invoices SET credit_amount = GREATEST(ROUND(credit_amount / fx, 4), 0.0001), rate = fx;
    UPDATE referral_rewards SET amount = ROUND(amount / fx, 4);
    UPDATE referral_recoveries SET outstanding = GREATEST(ROUND(outstanding / fx, 4), 0.0001);

    UPDATE deposit_methods SET min_deposit = CASE WHEN auto_verify = 'binance' THEN ROUND(min_deposit / fx, 4) ELSE min_deposit END,
                              rate_to_currency = CASE WHEN account_type = 'crypto' OR lower(name) LIKE '%binance%' THEN 1 ELSE fx END;

    UPDATE bot_settings SET value = 'USD' WHERE key = 'currency';
    UPDATE bot_settings SET value = '$' WHERE key = 'currency_symbol';
    UPDATE bot_settings SET value = '1' WHERE key = 'zinipay_rate';
    UPDATE bot_settings SET value = '1' WHERE key = 'binance_pay_rate';
    UPDATE bot_settings SET value = (ROUND(value::NUMERIC / fx, 4))::TEXT WHERE key IN ('referral_reward_amount', 'max_deposit_limit');
    INSERT INTO bot_settings (key, value) VALUES ('currency_cutover_rate', fx::TEXT)
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

    ALTER TABLE wallet_ledger ENABLE TRIGGER wallet_ledger_immutable;
    ALTER TABLE users ENABLE TRIGGER wallet_change;
END $$;

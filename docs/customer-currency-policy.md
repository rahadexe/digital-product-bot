# Customer currency display

The wallet, order prices, refunds and credits remain USD. Changing a customer preference changes presentation only; it never rewrites their balance.

## Payment examples

At the configured example rate of 125 BDT per USD:

| Preference | Method | Payment instruction | Wallet result |
| --- | --- | --- | --- |
| BDT | bKash / Nagad / Rocket | Send 500 ৳ | 500 ৳ added; no USD conversion copy |
| USD | bKash / Nagad / Rocket | Send 500 ৳; adds $4 | $4 added |
| BDT | Binance | Send 4 USDT; adds 500 ৳ | 500 ৳ added |
| USD | Binance | Send 4 USDT; adds $4 | $4 added |

USDT remains the Binance payment unit; its 1:1 USD settlement rate is not used as the BDT display rate. Local payment inputs and limits remain BDT regardless of display preference. Currency selection never changes the payment amount or backend conversion.

Profile, catalog, order/deposit history, balance adjustments, referral rewards, refunds, delivery receipts and deposit confirmations use the chosen display currency. USD amounts retain up to four decimal places. Normal BDT screens do not append USD equivalents. The legacy dual-display formatter remains available only when explicitly requested.

Preferences are read from the database, so a switch processed by one bot worker is visible to other workers without waiting for cache expiry. Historical messages already sent by Telegram are not retroactively rewritten; reopening the screen uses the current preference.

Regression coverage includes all four payment/preference combinations, real amount-entry handler state, checkout, background receipt formatting and cross-worker stale preferences. Real payment and PostgreSQL integration checks still require configured test services; no production balances were changed.

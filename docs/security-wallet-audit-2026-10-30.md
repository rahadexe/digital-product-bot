# Security, wallet and desktop audit — 30 October 2026

## Fixed findings

| Severity | Area | Problem and correction |
| --- | --- | --- |
| Critical | Statement webhooks | An unsigned ZiniPay statement could insert payment evidence used for automatic credit. Both statement endpoints now require a shared secret, including outside production, and fail closed when no secret exists. Invoice callbacks still trigger independent gateway verification and never insert statements. |
| High | Binance confirmation | A callback message is authored by the bot. The claim path now explicitly receives the clicking customer's ID instead of using the message author's ID. This also fixes an undefined variable in gateway-error handling. |
| Medium | Wallet reads | A recent cached user record could show a pre-deposit/pre-refund balance or outdated ban. Financial user reads now fetch the current database row. |
| Medium | Currency preference | Toggle read and write were separate, using cached state. They now run under a row lock without changing the wallet. Cold locale reads honor explicit currency, and cache hits no longer indefinitely renew stale language preferences. |
| Medium | Deposit reconciliation | A tolerance allowed up to 0.001 USD disagreement between payment and credit. Rounded four-decimal USD amounts must now match exactly. Non-finite, zero and negative quoted rates are rejected. |
| Medium | Statement input | Non-finite, oversized or rounded-to-zero amounts are rejected before persistence. Non-object SMS payloads return a client error, and stored transaction IDs use the existing validation rule. |
| Low | Wallet notification | Admin wallet adjustment notifications now format both delta and balance using the customer's currency preference. |

## UI polish

| Severity | Location | Before | After | Why |
| --- | --- | --- | --- | --- |
| Medium | console/src/app/(panel)/studio.css | Dark navy sidebar with a separate bright-purple selected state | White surface, shared purple accent/soft accent, shared text, divider, badge and hover tokens | Match the mobile palette and shared surface hierarchy; preserve responsive layout and existing controls |

Desktop screenshot: `scratch/audit-ui/audit-orders-1440.png`. Synthetic data only.

## Verification and limits

- Python suite: 447 passed, 207 skipped, 7 subtests passed.
- TypeScript check and Next.js production build passed.
- Responsive browser suite: 126 populated screen checks across 320–1440 px and interaction regressions passed.
- Extended layout suite passed on retry: 24 Home states, 24 delayed-loading transitions, two refresh cases, reduced motion, 24 exact-copy customer-input cases, and Stock/Deposits navigation. The first run timed out waiting for an order-detail control; a diagnostic rerun passed without product changes.
- Undefined-name lint check passed.
- UI verdict: Approve for the inspected sidebar palette and tested responsive screens. Every possible component state was not manually inspected.
- New regression coverage exercises forged statements, malformed amounts, invoice callbacks, currency cache expiry, fresh wallet reads, locked toggles, BDT notifications, Binance callback identity and exact deposit reconciliation.
- Database integration tests require a disposable local PostgreSQL instance; no local instance was available. These were skipped, not counted as passing. Live payments, production database state and deployment were not exercised.
- This is a source-and-test audit of the reviewed paths, not a claim that every security vulnerability has been eliminated.

## Deployment compatibility

SMS/statement senders must supply `X-Webhook-Secret` matching `sms_webhook_secret`, or the configured `webhook_secret` fallback. Existing Bearer and query-secret compatibility remains; prefer the header. Unsigned statement integrations will receive 401 until configured. Ordinary invoice callbacks remain unsigned because credit requires server-side gateway verification.

No production configuration, balances or external accounts were changed.

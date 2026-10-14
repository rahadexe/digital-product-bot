# Production readiness audit — 14 October 2026

Status: local fixes and regression checks completed; production sign-off is still conditional on the release gates below. No production deployment or live payment was performed. This is not a guarantee that every possible defect has been eliminated.

## Fixed in this audit

| Area | Finding and correction |
| --- | --- |
| Credentials | Removed a hardcoded Safwan Tiger API key from both source defaults. Supplier credentials now load from saved settings on startup and refresh before purchase. Removing a saved key no longer retains that old value after settings refresh; existing Digital Mart environment-key fallback remains supported. Changed credentials invalidate cached balances. Settings can remain cached for up to 30 seconds across processes, so external revocation is still necessary. The previously embedded credential must still be revoked externally. |
| Authorization | A cached customer profile could retain stale balance, rank or ban information. Security-sensitive profile reads now use the database. Cached channel membership no longer bypasses a new ban. |
| Customer API | All customers retain API access, as requested. Only approved resellers receive reseller prices. Checkout revalidates revoked API keys for ordinary customers as well as resellers. API onboarding documentation reflects this policy. |
| Supplier configuration | Unknown supplier codes are rejected before settings can be modified. Independent balance requests run concurrently, and unavailable balances display as unknown. |
| Supplier retries | Stable upstream request IDs replace timestamp IDs. An already accepted supplier order cannot be purchased again through retry. Timeout, malformed success and server-error outcomes are retained for reconciliation rather than silently repeated. The same customer request does not debit the wallet twice. |
| Supplier interruption recovery | Migration 0046 adds a durable attempt journal committed before the upstream call. Accepted responses survive a wallet rollback and are reused on the same request. Interrupted/unknown attempts cannot be automatically resent. A read-only reconciliation report identifies stalled attempts and accepted attempts without a local order. |
| Webhook | Non-ASCII secret headers now receive a rejection rather than triggering a comparison error. |
| Production settings | Reject wildcard trusted proxies, wildcard/empty host lists and unsafe cross-origin configuration in production. |
| Dependencies | Updated Next.js to 16.3.8 and PyJWT to 2.15.0; refreshed vulnerable transitive frontend packages. Runtime dependency audits reported no known vulnerabilities at audit time. |
| Bot flows | Fixed an invalid deposit service reference, stale guide handler name, duplicate conditional syntax and uninitialized language variables. Wallet language follows the current bot policy. Restored the ZiniPay master disable switch. |
| Background work | Bound menu tracking by chat/message count, limit cleanup call duration and cancel remaining notification tasks during shutdown. |
| Admin UI | Compact table layouts remain tables on mobile; category tables use an internal horizontal scroll area. Select keyboard navigation skips disabled options and uses accessible active-option semantics. Escape closes the open select before the dialog. Focus uses a single visible border. |
| Delivery tooling | Added backend/frontend CI checks, pinned test tools, and updated deployment instructions for the static console build and request-size limit. Hosted CI has not been executed by this audit. |

## Verification and evidence

Tests used isolated schemas in a disposable PostgreSQL instance bound to localhost. Payment, supplier and Telegram effects were mocked. Existing user data was not used for destructive testing.

- **Full local suite: 269 passed, 9 subtests passed, 0 failed** in 613.37 seconds. Two test-client deprecation warnings remain. Covers authorization, rate limiting, concurrency, payment validation, ledger integrity, migrations, buying, deposits, menus, search, Mini App and layout-related regressions. See `tmp/release-full-suite.log`.
- **Final supplier/credential checks: 30 passed**, covering the final credential-refresh changes as well as durable attempts, interruption handling, ownership/cache safeguards and adapter errors. See `tmp/final-supplier-regressions.log`. These overlap with the full suite; do not add the two counts as unique tests.
- Supplier recovery tests simulate a successful upstream purchase followed by local rollback and service reconstruction, and cancellation while an upstream request is in flight. They verify one upstream purchase and one wallet debit, accepted-response reuse, blocked uncertain retry, and explicit retry only after a definitive refusal. The read-only recovery report was also checked for orphan detection and absence of delivered credentials.
- Earlier failing logs are retained for traceability; their failures were repaired and rerun. Local PostgreSQL was version 18; the new hosted CI configuration uses PostgreSQL 17 and has not been executed here. Run CI against the exact revision to deploy.
- Critical Python checks: `ruff check app --select E9,F63,F7,F82` passed.
- Frontend production build, TypeScript validation and static export passed. See `tmp/release-console-build.log`.
- `npm audit` and the Python runtime dependency audit reported zero known vulnerabilities. See `tmp/python-audit-final.json`. This does not establish that application code has no vulnerabilities.

### Mobile/browser coverage

Checked Dashboard, Orders, Deposits, Customers, Products, Suppliers, Stock, Categories, Durations, Emojis, Broadcast, Reseller Apps, Activity and Settings at **320, 390, 768 and 1440 pixels**: 56 distinct page/viewport combinations, with no detected document overflow or application crash. Wide tables scroll inside their containers. Reseller Apps was rechecked at its correct `#reseller-apps` route after the first matrix used an invalid route.

Evidence: `tmp/mobile-audit-results.json`, `tmp/mobile-reseller-results.json`, and `tmp/audit-*.png`. These use synthetic browser API fixtures. They verify responsive rendering, not every live action or every physical device. Modal focus, select interaction and representative screenshots were also inspected. The latest supplier-review drawer was checked at 390px with the unsafe retry disabled (`tmp/supplier-review-mobile.png`). Live broadcast, synchronization, deletion, refunds and payment submission were not executed.

### Performance measurement

Local stock purchase benchmark: 100 orders, concurrency 10, 0.799 seconds total, approximately 125 orders/second, p50 16.08 ms and p95 432.79 ms. Wallet totals, order count and consumed stock were verified. See `tmp/purchase-benchmark.json`.

This measures the local purchase service only. It excludes Telegram latency, supplier APIs, queue waiting, production network latency and sustained load. It is not a production capacity claim.

### Rate limiting and request boundaries

Reviewed and exercised the existing database-backed request limits, login throttling, ownership checks, duplicate payment handling and body limits. Current HTTP API limit is 180 requests/minute per client; customer API reads/writes have separate user-based 120/30 limits. Rotating a key does not reset the user limit. General request bodies are capped at 2 MiB with a receive timeout; the Telegram webhook has its own smaller boundary and secret validation.

Correct client identification depends on the actual reverse-proxy configuration. That deployment boundary has not been verified on the production server.

## Release gates still open

1. **Revoke and replace the previously embedded supplier key.** Removing source defaults cannot invalidate a key already copied into Git history, logs, backups or another checkout. Rotate it in the supplier account, save the replacement through the existing secret settings, and review supplier usage. Do not paste it into source or this report.
2. **Verify supplier recovery operationally.** Durable intent and response storage now prevent blind retries through the tested interruption/rollback paths. An uncertain outcome still requires an operator to confirm the supplier's result; the bot cannot infer whether an external provider charged. Run the read-only report below and rehearse reconciliation before unattended supplier sales. Do not change the request ID to bypass an uncertain attempt. These tests do not prove the supplier's own idempotency contract or simulate every OS/database failure.
3. **Validate the actual hosting boundary.** Confirm HTTPS, Secure cookies, HSTS, expected hosts/origins, exact trusted proxy peers and firewall rules. Keep PostgreSQL and the application port private. Check that forged forwarding headers cannot change the rate-limit identity.
4. **Run a restore drill and live smoke test.** Restore an encrypted database backup into a separate environment, run migrations, verify ledger/order integrity, then test a controlled low-value deposit, purchase and refund with the real providers. Check webhook health, restart recovery, failed-job alerts and disk/connection monitoring.
5. **Freeze and test the release revision.** The workspace contains concurrent work. Run the new CI workflow against the exact revision to deploy, keep its output, and deploy its matching static console build. This audit did not execute hosted CI or certify later edits.

## Follow-up backlog

- Move external supplier calls out of wallet-lock transactions into a fulfillment worker; slow providers currently hold a main database connection and customer wallet lock. Journal commits use a separate lazy pool capped at two connections per process so they cannot deadlock behind a saturated main pool. Include those connections in server capacity planning.
- Add sustained production-like queue/load tests with the real hosting topology and representative database size.
- Consider tighter supplier outbound URL/network allowlists, shorter admin session lifetime and a nonce/hash-based CSP in place of inline-script allowances. These require deployment/product decisions and are not presented here as proven public exploits.
- Track the Starlette/httpx and AnyIO test-client deprecation warnings. They did not fail the checks.

No deployment was performed. No source change alone can certify the external release gates above.

## Supplier reconciliation procedure

After migration 0046, run `python -m app.db.scripts.supplier_reconciliation` in the deployed environment. It is read-only, excludes delivered credentials and lists at most 500 attempts older than five minutes. `possibly_truncated` means additional rows may remain.

For an uncertain attempt, check the supplier using the recorded provider request key and supplier order ID, if present. If a local waiting order exists, use the existing manual fulfillment/refund controls only after confirming the external result. If an accepted attempt has no local order, the original customer/request metadata is retained; replaying that same request can recover the saved supplier response without purchasing again. Confirm available balance and the original product first. Never delete the journal row or mark an unknown attempt as refused merely to enable retry.

The journal contains sensitive supplier responses in the database, like existing inventory/order credentials. Restrict database access and encrypt backups. It is deliberately not exposed through customer APIs.

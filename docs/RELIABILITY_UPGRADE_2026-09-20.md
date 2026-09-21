# Reliability upgrade — 20 September 2026

Follow-up: the owner confirmed all environments and orders are test data. See [security hardening](SECURITY_HARDENING_2026-09-20.md) for subsequent shared rate limits, cookie-only admin sessions, additional fixes and updated verification results.

## Delivery status

Fixes are present in the workspace. No production deployment, live database migration, real payment, or Telegram message was performed. The configured database was inspected read-only during the original audit. New migrations were exercised against isolated schemas in a disposable local PostgreSQL 17 instance.

The workspace changed concurrently during this task, including new reseller functionality and USD price display. Those features are retained. Include the new Python modules, migrations, tests and console lockfile when packaging the release; a tracked-files-only diff is incomplete.

## Preserved features

- Manual fulfillment and instant stock delivery, shared stock seats, customer order history and refunds.
- Manual deposit review, ZiniPay and Binance verification, flat referral rewards, current emoji management, reseller panel/API and secondary USD price display.
- Historical supplier orders retain their delivery records. Old supplier attempts are copied to the audit log before their table is removed.

## Removed features

Supplier service, supplier routes/configuration and catalog integration are removed. Migration `0023` drops supplier product columns and the attempts table after archiving attempts. It drops `media_assets`, `home_banners`, and `bot_welcome_banners`, and removes obsolete banner/supplier/percentage-referral/emoji-JSON settings. The active `custom_emojis` table is retained.

Earlier migration files intentionally retain the old schema definitions: they are immutable history needed to upgrade existing installations. A fresh migration run creates then retires those obsolete structures; they do not remain in the final schema. There was no evidence of multiple copies of the same table in the inspected database. One redundant inventory-order index is removed.

## Correctness and security changes

| Area | Change |
| --- | --- |
| Purchases | Quantity-aware retry keys, transactionally allocated stock seats, explicit allocation records for every stock row, SQL wallet arithmetic, concurrency checks against overselling. |
| History/refunds | Used stock survives product deletion; refunds are idempotent and cancel pending delivery. Previously spent legacy referral bonuses become explicit recovery records rather than forcing a negative wallet. |
| Wallet | Exact PostgreSQL NUMERIC ledger records opening balances and subsequent deltas; ordinary UPDATE/DELETE of ledger entries is rejected. Privileged database owners still require operational access controls. |
| Identity | New financial records cannot pair one customer's internal ID with another Telegram ID. Additional foreign keys protect future writes without deleting old rows. |
| ZiniPay transaction verification | Reserve the deposit before consuming the external transaction; persist confirmation state; recover confirmed credits and route ambiguous outcomes to review. Return success only after credit is persisted. Validate contradictory/malformed receipt responses. |
| Hosted invoices | Recover interrupted creation by reference, reject mismatched identities and invalid amounts, preserve a completed invoice against delayed creation errors, and provide a working return-to-bot page. |
| Binance | Correct BDT/USDT quote units and matching; stable payer UID alone cannot authorize credit. Fair scheduled checks prevent older pending payments from starving. |
| Reseller API | Fix stats table, serialize key rotation, enforce one active key, throttle last-used writes, check current reseller role while charging, require a retry key, escape dynamic documentation HTML. |
| Admin/verification abuse | Atomic database-backed login attempt budget and persistent verification failure budget; production requires an explicit persistent secret. |
| Telegram | Persist authenticated webhook updates before acknowledging them, deduplicate by update ID, process through bounded workers with customer ordering, leases and retries. Store conversation state in PostgreSQL unless Redis is configured. |
| Delivery | Retain unfinished broadcasts, support long credentials without invalid copy buttons, keep retries and payment checks isolated. |
| Migrations | Checksum applied files, serialize migration runs, adopt older migration history, scope repaired constraint checks to the correct schema. |

## Performance and scaling

Gateway HTTP clients reuse connections. Database acquisition and command timeouts bound resource waits. Background payment work is claimed in batches with leases; hosted invoice verification has bounded concurrency. Catalog caching is bounded, relevant history/due-work indexes are added, and expiry/dashboard queries are corrected. Cleanup removes expired security records and completed transient work without deleting financial history or pending jobs.

Webhook web replicas can share PostgreSQL inbox/state (or Redis state). Keep all replicas on the same code/configuration. Run exactly one long-polling bot if polling is used; polling does not have the durable webhook intake guarantees. A separate `worker` process handles payment reconciliation and outbound delivery. Multiple workers use database claims, but Telegram sends cannot be guaranteed exactly once after a network timeout.

These changes improve the foundation; no production latency or maximum user-count claim is made. Actual capacity depends on database network latency, pool capacity across **all** processes, Telegram/provider limits and host resources. Before raising traffic substantially, measure queue age, DB pool wait, API latency and payment reconciliation lag under representative load. Apply per-client/request-rate limits at the reverse proxy, especially for the public reseller API; keep the application port private and configure trusted proxies narrowly.

## Verification

Final local result: **32 integration tests passed in 78.816 seconds**, including the historical upgrade test. Console production build passed; Python compilation, `pip check` and `git diff --check` passed (Git emitted only Windows line-ending notices). No live provider or production load test was run.

Run against an explicitly selected disposable local database (the suite refuses remote hosts):

```powershell
$env:TEST_DATABASE_URL = 'postgresql://postgres@127.0.0.1:55439/postgres'
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Every test creates and removes its own schema and mocks external gateways. Coverage includes concurrent purchases/stock imports/key rotation, retry-safe credits, shared seats, manual delivery/refunds, immutable wallet deltas, customer isolation, durable webhook replay, conversation restart, rate budgets, stale verification recovery, payment fairness, historical upgrade and changed-migration detection. Console `npm run build` also checks TypeScript and builds the production bundle. See the task result for final test counts.

## Release procedure

1. Back up the database and verify restore access. Package all changed and newly added files together.
2. Pause intake and stop the old bot/web/worker processes. This release removes schema objects that old code may reference, so do not run mixed versions through the cleanup migration. Do not discard pending Telegram updates.
3. Set production configuration: stable `SECRET_KEY`, strong `ADMIN_PASSWORD`, database URL, HTTPS webhook origin and correct trusted proxy/host settings. Preserve existing gateway credentials. BDT remains the wallet currency; USD is display-only. Set `AUTO_MIGRATE=false` for ordinary service starts.
4. With the release environment, run `python -m app migrate` once. It applies migrations in a transaction. For large production tables, assess the migration lock/backfill duration on a restored copy and allow sufficient command timeout/maintenance time.
5. Start the new `web` and `worker` roles (or one `all` process). Verify readiness, then resume intake. Check one controlled manual order, instant order, deposit and retry before increasing traffic.
6. Watch failed inbox/outbox jobs, ambiguous payment attempts and oldest pending payment age. Review ambiguous gateway outcomes against the merchant statement before approving; do not ask customers to pay twice. Retain explicit recovery records until resolved.

## Remaining operational limits

- Local tests do not replace production gateway sandbox checks, a deployment smoke test, recovery drills or load measurement.
- Historical multi-item quantities/links that were never stored cannot be reliably reconstructed. New orders store them explicitly; unknown old quantities remain NULL in the database.
- New NOT VALID constraints protect future writes; separately audit old rows before validating the full historical dataset.
- Historical supplier audit records and delivered credentials are intentionally retained; protect database/backups and operator access accordingly.
- PostgreSQL stores monetary values exactly, but some application formatting/calculation paths still use four-decimal rounded floats. An end-to-end Decimal conversion is a separate compatibility change.
- Caches can remain stale for their configured short TTL across replicas. Failed inbox work requires operational review after the retry limit; no new operator UI for replay was added.
- Rollback after destructive feature cleanup requires restoring the database backup along with compatible code, not merely deploying the old application image.

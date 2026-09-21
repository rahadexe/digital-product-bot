# Handler crashes, request boundaries and query scaling — 21 September 2026

This round follows the [reliability upgrade](RELIABILITY_UPGRADE_2026-09-20.md) and
[security hardening](SECURITY_HARDENING_2026-09-20.md). Those changes were correct but had never been
committed, and the linter that would have caught the defects below was not part of the project.

## What was broken

### Five undefined names on live button paths

Each of these raised `NameError` the moment a customer pressed the button that the bot itself had
just drawn. None was covered by the integration suite, which exercises services rather than message
rendering.

| Location | Name | Reached by |
| --- | --- | --- |
| `app/bot/handlers/shop.py` | `ICON_CHECK` (twice) | the purchase confirmation, after the wallet was charged |
| `app/bot/handlers/profile.py` | `ICON_PRODUCTS`, `ICON_CART` | opening the Reseller Panel |
| `app/bot/handlers/deposit.py` | `PAYMENT_REFERENCE` | "I've Paid — Check" on a hosted invoice |
| `app/bot/handlers/deposit.py` | `ICON_QUESTION` | "Where to find your Order ID?" on the Binance screen |

The purchase one was the worst. The order committed, the wallet was debited and the receipt reached
the durable outbox, then rendering the confirmation threw. The inbox worker treated the update as
failed and retried it five times; `request_id` kept those retries idempotent, so no customer was
charged twice, but the tapped button never changed and every purchase left a failed inbox row.

`ICON_QUESTION` did not exist at all and was added to `app/bot/icons.py` from the `Icons.QUESTION`
id already declared there. `PAYMENT_REFERENCE` now matches the `SM` + 16 hex reference that
`PaymentService.create_invoice` issues, the same shape the admin route already validated.

### CORS could not see the security boundary's rejections

Starlette runs the last middleware added outermost, and the order was CORS, SecurityBoundary,
TrustedHost — which put CORS *innermost*. Every response SecurityBoundary returned itself (429, 413,
408, the origin 403 and the 503 when a shared budget cannot be read) therefore went out without
`Access-Control-Allow-Origin`. A console on another origin saw an opaque CORS failure instead of the
real status and `Retry-After`. The three are now added innermost-first so CORS wraps the boundary.

### Admin alerts pointed at localhost, and were lost with the button

Seven call sites built an operator link as
`webhook_base_url or webapp_url or "http://127.0.0.1:8000"`. With no public address configured the
inline button named a private address, which Telegram refuses; `Notifier.send` swallows that refusal
and returns `False`, so the whole order or deposit alert vanished without an operator-visible error.

`Settings.console_url` now returns the public https origin or an empty string, and each caller drops
the button rather than linking somewhere only the server can open. `WEBAPP_URL` contributes only its
origin, since that setting is stored pointing at `/app/`.

## Query and write-path scaling

Migration `0028_search_and_write_scaling` adds:

- `audit_logs(action)`, because the audit page lists every distinct action on each search and was
  reading the whole log to do it.
- Trigram GIN indexes on `orders.product_title`, `users.username` and `audit_logs.details`, so the
  console's `ILIKE '%term%'` searches stop being sequential scans. Measured on 50 000 seeded orders:
  `Bitmap Index Scan on orders_title_search`, 6.3 ms, against a 20.9 ms sequential scan. The gap
  grows with the table; the sequential scan is linear and the index is not.
- `fillfactor` and tighter autovacuum thresholds on `request_limits`, `bot_conversations`,
  `telegram_inbox` and `outbox`. All four are updated far more often than inserted into — a
  rate-limit row per API request, a conversation row per bot tap — and the free space lets
  PostgreSQL update in place instead of writing a new row version plus every index entry.

An extension belongs to the database rather than to a schema, so `CREATE EXTENSION IF NOT EXISTS
pg_trgm` silently does nothing when pg_trgm already lives somewhere outside the connection's
`search_path`, and an unqualified `gin_trgm_ops` then fails to resolve. The migration therefore looks
the extension's schema up and names the operator class explicitly. If the extension cannot be
installed at all — a role without permission — the whole block raises a notice and is skipped, and
search keeps the plan it has today.

## Tooling

`ruff` is now a declared dev dependency (`pip install -e ".[dev]"`) and the project is clean under
its own configuration. The five crashes above were all `F821`; nothing but the absence of a linter
kept them in the tree. Also fixed while there: `zip()` in the force-join check is now `strict=True`,
so a missing membership result fails loudly instead of quietly admitting a customer; the two
`MockTransport` closures in the suite bind their loop variables; the deposit fallback message shows
the request ID it already had; and the security-actions filter in the audit view now matches the
`deposit_amount_adjusted`, `referral_recovery_needed` and `supplier_history_archived` entries that
newer code writes.

## Verification

- 46 integration tests pass against a disposable local PostgreSQL 17 instance.
- All 29 migrations replay onto a fresh schema; index and table settings confirmed in `pg_indexes`
  and `pg_class.reloptions`.
- `ruff check app tests scripts` clean; `compileall` clean.
- Console `tsc --noEmit` and the optimized production build pass.
- `console/package-lock.json` is committed and in sync with `package.json`, which the Dockerfile's
  `npm ci` requires.

Not verified: real Telegram sends, real gateway calls, and index behaviour on production-sized data.
The search measurement above is a local seed, not a production benchmark.

## Still open

These need a decision rather than a patch, and are unchanged from the earlier audit:

- Monetary values still round-trip through four-decimal floats in formatting and calculation paths,
  although PostgreSQL and the wallet ledger keep them exact.
- Every `/api/` request spends one database round trip on the shared rate-limit budget. That is what
  makes the limit hold across replicas; on a single replica behind a proxy that already limits, it is
  latency with little return.
- `Throttle`, the force-join membership cache and the catalog/settings caches remain per process.
- A broadcast still copies its full text once per recipient.
- Order, deposit and user list endpoints recompute full-table aggregates for their summary cards.

# Architecture

One codebase runs three roles from `python -m app <role>`: `web` (HTTP API, Telegram webhook intake
and the static console), `worker` (payment reconciliation and outbound delivery), and `all`, which
runs both in one process. `migrate` applies pending migrations and exits.

## Layout

```
app/
  api/          FastAPI routes. admin/ is the console API, reseller.py the public one,
                telegram.py the webhook, payments.py the gateway callbacks.
  bot/          aiogram dispatcher, handlers, keyboards and the Telegram icon table.
  core/         Process configuration, logging, money helpers.
  db/           Connection pool and the numbered SQL migrations.
  services/     Every read and write of the database goes through here.
  workers/      Long-running loops: outbox delivery, payment checks, Telegram inbox.
console/        Next.js operator console, exported as static files and served by the API.
docs/           Audits, upgrade notes and this file.
scripts/        Operator scripts; see scripts/README.md.
tests/          Integration tests against a disposable local PostgreSQL.
```

Routes and handlers never touch the database directly. They call a service, and the service owns the
transaction. That is what lets one purchase path serve the bot and the reseller API without either
of them knowing how stock is claimed.

## Where configuration lives

Two places, split by what changes and how often.

**`.env` — what the process needs to start.** Database URL, bot token, the public origin, and the
secrets that protect the console (`ADMIN_PASSWORD`, `SECRET_KEY`). Changing any of these means a
restart, which is correct: they define the deployment, not the shop.

**The admin console — how the store behaves.** Admin Telegram IDs, gateway API keys and rates,
prices, payment methods, referral rewards, channels, the welcome and guide text, the pause switch.
These live in `bot_settings`, are declared once in `app/services/settings.py` with a default and a
validator, and take effect without a redeploy.

`SPECS` in that module is the single list of what the store can be told. A key that is not declared
there is rejected by the settings endpoint, so the console cannot write arbitrary rows. Keys marked
`secret=True` are write-only: the API returns them masked (`81a8****…4b27`) and a masked value
submitted back is ignored, so re-saving the form never overwrites a key with its own placeholder.

A few settings also exist as environment variables — `ADMIN_TG_ID`, `ZINIPAY_API_KEY`,
`BINANCE_API_KEY`, `BINANCE_API_SECRET`. These are a fallback for an automated first deploy that has
no console yet. **The console value wins whenever it is set.** Keeping a stale value in `.env`
alongside a console value is the one configuration mistake this split invites; leave the environment
variables empty once the console has them.

## How a purchase holds together

`PurchaseService.purchase` runs the whole thing in one transaction: lock the customer, re-read the
price from the database (never from the caller), check the balance, claim stock seats with
`FOR UPDATE SKIP LOCKED`, charge the wallet, write the order and its allocation rows, and queue the
customer's message in the outbox. A `request_id` makes a retry return the original order instead of
buying twice.

The receipt is not sent inside that transaction. It is inserted into `outbox`, and the delivery
worker claims it with a lease. A crash between commit and send costs a retry, never the order.

## Durability

| Concern | Mechanism |
| --- | --- |
| Telegram updates | Persisted to `telegram_inbox` before the webhook answers 200, deduplicated by update id, processed by bounded workers with leases and per-customer ordering |
| Outbound messages | `outbox` rows claimed with a lease; order receipts sort ahead of broadcasts |
| Wallet | `wallet_ledger` records the exact NUMERIC delta of every balance change; a trigger rejects UPDATE and DELETE of its own rows |
| Gateway confirmation | The deposit is reserved before the external transaction is consumed, and `payment_verification_attempts` carries the state so an interrupted confirmation is recovered rather than re-charged |
| Conversation state | PostgreSQL by default, Redis when `REDIS_URL` is set — so webhook replicas can share it |

## Request boundaries

`SecurityBoundary` runs before routing: local flood protection, then a shared per-IP budget in
`request_limits` so the limit holds across replicas, body size and whole-upload timeout, Origin
checks on writes, and the security headers. Authenticated resellers get their own read and write
budgets keyed to the account, so rotating a key or changing IP does not reset them.

Middleware order is TrustedHost, CORS, SecurityBoundary. CORS must stay outside the boundary or the
rejections the boundary returns itself reach a cross-origin console without CORS headers, and the
browser reports an opaque failure instead of the real status.

## Database

Migrations are numbered files applied in filename order inside one transaction, under an advisory
lock, each recorded with a checksum. Editing an applied file is refused — write a new one.

Money is `NUMERIC` in PostgreSQL. Some application formatting and calculation paths still round
through four-decimal floats; converting those end to end is a separate change.

### What already scales

- Every hot query has an index: due-work partial indexes for the outbox, inbox and payment
  schedules, customer history indexes on orders and deposits, and a seat-order index on inventory.
- Admin `ILIKE '%term%'` search uses trigram GIN indexes rather than sequential scans.
- The four tables that are updated far more often than inserted into (`request_limits`,
  `bot_conversations`, `telegram_inbox`, `outbox`) carry a lower `fillfactor` and tighter autovacuum
  thresholds, so steady traffic updates rows in place instead of bloating the table.
- Catalog and settings reads are cached for a short TTL, bounded in size.

### What will need attention as the store grows

These are known and deliberate, not oversights. Each is a design decision rather than a patch:

1. **Money as float in application code.** PostgreSQL and the ledger keep exact values, but
   formatting and some arithmetic round through floats. Moving to `Decimal` or integer minor units
   end to end is a compatibility change across every service and the console.
2. **Full-table aggregates behind the summary cards.** The order, deposit and user list endpoints
   recompute `COUNT`/`SUM` over the whole table on every page load. At tens of thousands of rows
   these want incremental counters or a periodically refreshed summary table.
3. **Broadcast storage.** Each broadcast copies its full text once per recipient. A shared payload
   with per-recipient state would make storage grow with recipients, not with recipients × length.
4. **Per-process state.** Throttling, the force-join membership cache and the catalog caches are
   per process. More replicas means each keeps its own; shared state belongs in Redis.
5. **One database round trip per API request** for the shared rate-limit budget. That is what makes
   the limit correct across replicas. On a single replica behind a proxy that already limits, it is
   latency with little return.
6. **Retention.** Orders, deposits and audit logs grow without bound by design, because they are
   financial history. Archival or partitioning is the answer, not deletion.

## Testing

`tests/` runs against a disposable local PostgreSQL; the suite refuses a remote host. Every test
creates and drops its own schema and mocks the gateways.

```bash
TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres python -m unittest discover -s tests
ruff check app tests scripts
cd console && npm run build
```

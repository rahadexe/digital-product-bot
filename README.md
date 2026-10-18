# customer-bot

A Telegram storefront for digital subscriptions: a customer bot, a wallet with manual and automatic
top-ups, instant delivery from local stock, a reseller API, and a Next.js operator console.

Python 3.12, FastAPI, aiogram 3, PostgreSQL. One image, one database, no external queue.

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env            # then fill in BOT_TOKEN, DATABASE_URL, ADMIN_PASSWORD, SECRET_KEY
python -m app migrate           # apply database migrations
python -m app                   # web + worker in one process
```

`python -m app <role>` takes `all` (the default), `web`, `worker` or `migrate`. Deployment, reverse
proxy and systemd setup are in [DEPLOYMENT.md](DEPLOYMENT.md); the container build is in the
`Dockerfile`.

## Developing

```bash
pip install -e ".[dev]"
ruff check app tests scripts

# The suite refuses remote hosts; point it at a disposable local database.
TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres python -m unittest discover -s tests

cd console && npm ci && npm run dev     # console on :3000, API on :8000
```

## Supplier setup

Open **Suppliers** in the admin panel. Each supported provider has an **Add API**
or **Edit API** button. Enter its HTTPS API base URL and key, then choose
**Save & connect**. A blank key keeps the saved key. The connection check makes
a fresh, read-only balance request; saving settings never places an order.

Digital Mart and Safwan Tiger use separate API adapters, credentials, currencies,
markup and auto-sync switches. A different provider needs its own documented
adapter, not just an arbitrary URL.

Use **Browse catalog** to select products and import them. Imports are hidden
unless activation is selected. **Sync** and background sync update only products
already imported, preserving custom titles, categories and higher selling prices.
Invalid keys, unavailable catalogs and missing selected products are reported as
errors, not successful zero-product imports.

Orders accepted by a supplier or with an unknown payment outcome must be checked
with that supplier before retrying. They are never automatically purchased again.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) — layout, durability, and what will need attention as the store grows
- [Reseller API guide](docs/reseller_api_guide.md) — the public API, also served at `/api/v1/reseller/docs`
- [Deployment](DEPLOYMENT.md) — VPS, reverse proxy, systemd

### Change history

- [Security review and payment-path attack tests](docs/SECURITY_REVIEW_2026-09-21.md)
- [Handler crashes, request boundaries and query scaling](docs/HANDLER_AND_SCALE_FIXES_2026-09-21.md)
- [Admin console layout and copy review](docs/ADMIN_UI_REVIEW_2026-09-21.md)
- [Pre-production security and rate-limit hardening](docs/SECURITY_HARDENING_2026-09-20.md)
- [Reliability changes, validation and release procedure](docs/RELIABILITY_UPGRADE_2026-09-20.md)
- [Original database and code audit](docs/PROJECT_AUDIT_2026-09-20.md)

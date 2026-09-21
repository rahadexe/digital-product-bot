# customer-bot

Python Telegram commerce bot with a Next.js operator console.

```bash
pip install -r requirements.txt          # runtime
pip install -e ".[dev]"                  # adds ruff
ruff check app tests scripts             # catches undefined names before a customer does

# The suite refuses remote hosts; point it at a disposable local database.
TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres python -m unittest discover -s tests
```

- [Handler crashes, request boundaries and query scaling](docs/HANDLER_AND_SCALE_FIXES_2026-09-21.md)
- [Reliability changes, validation and release procedure](docs/RELIABILITY_UPGRADE_2026-09-20.md)
- [Pre-production security and rate-limit hardening](docs/SECURITY_HARDENING_2026-09-20.md)
- [Admin console layout and copy review](docs/ADMIN_UI_REVIEW_2026-09-21.md)
- [Original database and code audit](docs/PROJECT_AUDIT_2026-09-20.md)
- [Reseller API guide](docs/reseller_api_guide.md)

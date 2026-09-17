"""Versioned SQL migrations in ``migrations/``, applied in filename order."""

from __future__ import annotations

import logging
from pathlib import Path

from app.db.database import Database

logger = logging.getLogger("app.db.migrations")

MIGRATIONS_DIR = Path(__file__).with_name("migrations")
# Any constant works; it only has to be unique to this application.
MIGRATION_LOCK_KEY = 7302114551


async def migrate(db: Database) -> list[str]:
    """Apply pending migrations in one transaction; concurrent deployments wait on the lock."""
    await db.ensure_schema()
    applied_now: list[str] = []
    async with db.transaction() as conn:
        await conn.execute("SELECT pg_advisory_xact_lock($1)", MIGRATION_LOCK_KEY)
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        applied = {row["version"] for row in await conn.fetch("SELECT version FROM schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.stem in applied:
                continue
            await conn.execute(path.read_text(encoding="utf-8"))
            await conn.execute("INSERT INTO schema_migrations (version) VALUES ($1)", path.stem)
            applied_now.append(path.stem)
    for version in applied_now:
        logger.info("Applied migration %s", version)
    return applied_now

"""Versioned SQL migrations in ``migrations/``, applied in filename order."""

from __future__ import annotations

import logging
import hashlib
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
        await conn.execute("ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum TEXT")
        applied = {row["version"]: row['checksum'] for row in await conn.fetch("SELECT version,checksum FROM schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            sql = path.read_text(encoding="utf-8")
            digest = hashlib.sha256(sql.encode()).hexdigest()
            if path.stem in applied:
                if applied[path.stem] and applied[path.stem] != digest:
                    raise RuntimeError(f"Applied migration changed: {path.name}. Create a new migration instead.")
                if not applied[path.stem]:
                    await conn.execute("UPDATE schema_migrations SET checksum=$2 WHERE version=$1", path.stem, digest)
                continue
            await conn.execute(sql)
            await conn.execute("INSERT INTO schema_migrations (version,checksum) VALUES ($1,$2)", path.stem, digest)
            applied_now.append(path.stem)
    for version in applied_now:
        logger.info("Applied migration %s", version)
    return applied_now

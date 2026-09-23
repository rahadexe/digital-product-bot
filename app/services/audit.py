"""Append-only record of administrative and money-moving actions."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

import asyncpg

from app.db import Database

actor = ContextVar("audit_actor", default="system")

# Sign-ins, bans, refunds, money that needed a second look and anything removed.
# supplier_* and referral_recovery_* are retired or rare, but old entries still carry them and the
# security view is the one place an operator goes looking for them.
SECURITY_ACTIONS = (
    r"^(login_|user_banned|reject_deposit|deposit_check_flagged|deposit_amount_adjusted|payment_failed|refund_order"
    r"|referral_recovery_needed|order_waiting|order_supplier|supplier_retry|supplier_history_archived|adjust_balance"
    r"|.*_deleted$|.*_removed$)"
)


async def record(conn: asyncpg.Connection, action: str, details: str) -> None:
    """Write an audit entry inside the caller's transaction, so it commits with the change."""
    await conn.execute("INSERT INTO audit_logs (action, details, actor) VALUES ($1, $2, $3)", action, details[:2000], actor.get())


class AuditService:
    def __init__(self, db: Database):
        self.db = db

    async def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        async with self.db.connect() as conn:
            return [dict(row) for row in await conn.fetch("SELECT * FROM audit_logs ORDER BY id DESC LIMIT $1", limit)]

    async def search(
        self, *, search: str = "", action: str = "", security_only: bool = False, limit: int = 50, offset: int = 0
    ) -> dict[str, Any]:
        """The whole log, filtered in the database: a search used to look only at the latest fifty entries."""
        where, params = [], []
        if search:
            params.append(f"%{search}%")
            where.append(f"(action ILIKE ${len(params)} OR details ILIKE ${len(params)})")
        if action:
            params.append(action)
            where.append(f"action = ${len(params)}")
        if security_only:
            params.append(SECURITY_ACTIONS)
            where.append(f"action ~ ${len(params)}")
        clause = f" WHERE {' AND '.join(where)}" if where else ""
        async with self.db.connect() as conn:
            rows = await conn.fetch(
                f"SELECT *, COUNT(*) OVER () AS total_count FROM audit_logs{clause} ORDER BY id DESC "
                f"LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
                *params,
                limit,
                offset,
            )
            actions = [row["action"] for row in await conn.fetch("SELECT DISTINCT action FROM audit_logs ORDER BY action")]
        return {
            "entries": [{key: value for key, value in row.items() if key != "total_count"} for row in rows],
            "total": rows[0]["total_count"] if rows else 0,
            "actions": actions,
        }

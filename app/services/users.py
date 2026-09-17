"""Customer accounts, referrals, wallet adjustments and bans."""

from __future__ import annotations

from html import escape
from typing import Any

from app.core.money import money
from app.db import Database
from app.services.audit import record
from app.services.errors import InvalidInputError
from app.services.notifications import Notifier
from app.services.settings import SettingsService

STATS_COLUMNS = ("order_count", "completed_total", "referral_count", "referral_earnings")


class UserService:
    def __init__(self, db: Database, settings: SettingsService, notifier: Notifier):
        self.db = db
        self.settings = settings
        self.notifier = notifier

    async def sync_profile(
        self,
        tg_user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        referred_by: int | None = None,
    ) -> dict[str, Any]:
        """Create or refresh a customer. A referrer is recorded only on creation."""
        if referred_by == tg_user_id:
            referred_by = None
        async with self.db.connect() as conn:
            # Only an existing, unbanned customer can refer; checked in the same statement.
            row = await conn.fetchrow(
                """
                INSERT INTO users (tg_user_id, username, first_name, last_name, referred_by)
                VALUES ($1, $2, $3, $4,
                        (SELECT tg_user_id FROM users WHERE tg_user_id = $5 AND is_banned = 0))
                ON CONFLICT (tg_user_id) DO UPDATE
                SET username = EXCLUDED.username, first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name, updated_at = now()
                RETURNING *
                """,
                tg_user_id,
                username,
                first_name,
                last_name,
                referred_by,
            )
            return dict(row)

    async def get(self, tg_user_id: int) -> dict[str, Any] | None:
        async with self.db.connect() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE tg_user_id = $1", tg_user_id)
            return dict(row) if row else None

    async def stats(self, tg_user_id: int) -> dict[str, Any]:
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                """
                SELECT u.*,
                    (SELECT COUNT(*) FROM orders o WHERE o.tg_user_id = u.tg_user_id AND o.status = 'completed') AS order_count,
                    (SELECT COALESCE(SUM(o.price), 0) FROM orders o
                     WHERE o.tg_user_id = u.tg_user_id AND o.status = 'completed') AS completed_total
                FROM users u WHERE u.tg_user_id = $1
                """,
                tg_user_id,
            )
        if not row:
            return {}
        values = dict(row)
        return {
            "user": {key: value for key, value in values.items() if key not in ("order_count", "completed_total")},
            "order_count": values["order_count"],
            "total_spent": values["completed_total"],
        }

    async def list(
        self, search: str = "", filter_type: str | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
        where_clauses, params = [], []
        if search:
            params.append(f"%{search}%")
            where_clauses.append(f"(username ILIKE ${len(params)} OR first_name ILIKE ${len(params)} OR last_name ILIKE ${len(params)} OR CAST(tg_user_id AS TEXT) LIKE ${len(params)})")
        if filter_type == "has_balance":
            where_clauses.append("balance > 0")
        elif filter_type == "banned":
            where_clauses.append("is_banned = 1")

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        async with self.db.connect() as conn:
            total = await conn.fetchval(f"SELECT COUNT(*) FROM users{where_sql}", *params)
            rows = await conn.fetch(
                f"SELECT * FROM users{where_sql} ORDER BY id DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}",
                *params,
                limit,
                offset,
            )
            summary_row = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) AS total_users,
                    COALESCE(SUM(balance), 0)::float AS total_balance,
                    COUNT(CASE WHEN balance > 0 THEN 1 END) AS with_balance_count,
                    COUNT(CASE WHEN is_banned = 1 THEN 1 END) AS banned_count
                FROM users
                """
            )
        summary = {
            "total_users": int(summary_row["total_users"] or 0) if summary_row else 0,
            "total_balance": round(float(summary_row["total_balance"] or 0.0), 2) if summary_row else 0.0,
            "with_balance_count": int(summary_row["with_balance_count"] or 0) if summary_row else 0,
            "banned_count": int(summary_row["banned_count"] or 0) if summary_row else 0,
        }
        return [dict(row) for row in rows], total, summary

    async def adjust_balance(
        self, tg_user_id: int, delta: float, reason: str = "", *, notify: bool = False
    ) -> dict[str, Any] | None:
        delta = money(delta)
        async with self.db.transaction() as conn:
            row = await conn.fetchrow("SELECT balance FROM users WHERE tg_user_id = $1 FOR UPDATE", tg_user_id)
            if not row:
                return None
            new_balance = round(row["balance"] + delta, 4)
            if new_balance < 0:
                raise InvalidInputError("Adjustment would make the wallet negative.")
            user = await conn.fetchrow(
                "UPDATE users SET balance = $1, updated_at = now() WHERE tg_user_id = $2 RETURNING *",
                new_balance,
                tg_user_id,
            )
            await record(
                conn,
                "adjust_balance",
                f"Adjusted balance of {tg_user_id} by {delta:+.2f} (new balance: {new_balance:.2f}). Reason: {reason}",
            )
        if notify:
            self.notifier.in_background(self._notify_adjustment(tg_user_id, delta, user["balance"], reason))
        return dict(user)

    async def _notify_adjustment(self, tg_user_id: int, delta: float, balance: float, reason: str) -> None:
        symbol = escape(await self.settings.get("currency_symbol"))
        action = "credited to" if delta >= 0 else "deducted from"
        await self.notifier.send(
            tg_user_id,
            f"💳 <b>Balance Adjustment</b>\n\n"
            f"An amount of <b>{symbol}{abs(delta):.2f}</b> was {action} your wallet.\n"
            f"💰 <b>Current Balance:</b> <code>{symbol}{balance:.2f}</code>\n"
            f"📝 <b>Reason:</b> {escape(reason or 'Admin adjustment')}",
        )

    async def set_banned(self, tg_user_id: int, banned: bool | None = None) -> bool:
        """Set or toggle a ban; returns the resulting state (False when the user does not exist)."""
        async with self.db.transaction() as conn:
            row = await conn.fetchrow("SELECT is_banned FROM users WHERE tg_user_id = $1 FOR UPDATE", tg_user_id)
            if not row:
                return False
            value = int(banned) if banned is not None else (0 if row["is_banned"] else 1)
            if value != row["is_banned"]:
                await conn.execute("UPDATE users SET is_banned = $1 WHERE tg_user_id = $2", value, tg_user_id)
                await record(conn, "user_banned" if value else "user_unbanned", f"User {tg_user_id}")
            return bool(value)

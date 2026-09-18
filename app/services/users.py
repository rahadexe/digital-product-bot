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
from app.bot.icons import (
    ICON_ACCOUNT,
    ICON_BALANCE,
    ICON_COIN,
    ICON_DEPOSIT,
    ICON_ID,
    ICON_NOTE,
    ICON_ORDERS,
    ICON_SPENT,
)

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
                RETURNING *, (xmax = 0) AS is_new
                """,
                tg_user_id,
                username,
                first_name,
                last_name,
                referred_by,
            )
            result = dict(row)
            if row["is_new"]:
                cust = f"@{escape(username)}" if username else "No username"
                full_name = escape(" ".join(filter(None, [first_name, last_name])) or "New User")
                self.notifier.in_background(
                    self.notifier.send_admin(
                        f"{ICON_ACCOUNT} <b>New Customer Joined</b>\n"
                        f"━━━━━━━━━━━━━━━━━━\n"
                        f"{ICON_ACCOUNT} <b>Name:</b> {full_name}\n"
                        f"{ICON_ACCOUNT} <b>Username:</b> {cust}\n"
                        f"{ICON_ID} <b>Telegram ID:</b> <code>{tg_user_id}</code>",
                        event="new_user",
                    )
                )
            return result

    async def process_referral_reward(self, tg_user_id: int) -> dict[str, Any] | None:
        """
        If user was referred by someone and the referral bonus hasn't been credited yet,
        credits the referrer's balance by referral_reward_amount and sends them an instant notification.
        """
        enabled = await self.settings.flag("referral_enabled")
        if not enabled:
            return None

        reward_amount = await self.settings.number("referral_reward_amount")
        if reward_amount <= 0:
            return None
        reward_amount = min(reward_amount, 100.0)

        async with self.db.transaction() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE tg_user_id = $1 FOR UPDATE", tg_user_id)
            if not user or not user["referred_by"] or user.get("referral_rewarded"):
                return None

            referrer_id = user["referred_by"]
            if referrer_id == tg_user_id:
                return None

            referrer = await conn.fetchrow("SELECT * FROM users WHERE tg_user_id = $1 FOR UPDATE", referrer_id)
            if not referrer or referrer["is_banned"]:
                return None

            existing = await conn.fetchrow("SELECT id FROM referral_rewards WHERE referred_tg_id = $1", tg_user_id)
            if existing:
                await conn.execute("UPDATE users SET referral_rewarded = 1 WHERE tg_user_id = $1", tg_user_id)
                return None

            await conn.execute(
                "INSERT INTO referral_rewards (referrer_tg_id, referred_tg_id, amount) VALUES ($1, $2, $3)",
                referrer_id, tg_user_id, reward_amount
            )
            await conn.execute(
                """
                UPDATE users
                SET balance = balance + $1,
                    referral_count = referral_count + 1,
                    referral_earnings = referral_earnings + $1,
                    updated_at = now()
                WHERE tg_user_id = $2
                """,
                reward_amount, referrer_id
            )
            await conn.execute("UPDATE users SET referral_rewarded = 1, updated_at = now() WHERE tg_user_id = $1", tg_user_id)
            await record(conn, "referral_reward_paid", f"User #{referrer_id} received {reward_amount:.2f} for referring #{tg_user_id}")

        symbol = await self.settings.get("currency_symbol")
        joined_name = escape(" ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or (f"@{user['username']}" if user.get("username") else "A friend"))
        reward_str = f"{reward_amount:g} {symbol}" if reward_amount == int(reward_amount) else f"{reward_amount:.2f} {symbol}"
        self.notifier.in_background(
            self.notifier.send(
                referrer_id,
                f"{ICON_ORDERS} <b>Referral Bonus Received!</b>\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{ICON_ACCOUNT} <b>Friend:</b> {joined_name}\n"
                f"{ICON_COIN} <b>Bonus Credited:</b> <code>+{reward_str}</code>",
            )
        )
        return {"referrer_id": referrer_id, "amount": reward_amount}

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
        action_type = "Credit Added" if delta >= 0 else "Balance Deducted"
        await self.notifier.send(
            tg_user_id,
            f"{ICON_DEPOSIT} <b>Wallet Balance Updated</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{ICON_COIN} <b>{action_type}:</b> <code>{delta:+.2f} {symbol}</code>\n"
            f"{ICON_BALANCE} <b>Current Balance:</b> <code>{balance:.2f} {symbol}</code>\n"
            f"{ICON_NOTE} <b>Reason:</b> {escape(reason or 'Admin adjustment')}",
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

    async def set_rank(self, tg_user_id: int, rank: str) -> str:
        """Update customer rank/role (Standard, Affiliate, Reseller, VIP)."""
        valid_ranks = {"Standard", "Affiliate", "Reseller", "VIP"}
        clean_rank = rank.strip().title()
        if clean_rank not in valid_ranks:
            clean_rank = "Standard"
        async with self.db.transaction() as conn:
            await conn.execute("UPDATE users SET rank = $1, updated_at = now() WHERE tg_user_id = $2", clean_rank, tg_user_id)
            await record(conn, "user_rank_updated", f"User #{tg_user_id} rank set to {clean_rank}")
        return clean_rank

"""Customer accounts, referrals, wallet adjustments and bans."""

from __future__ import annotations

import time
from collections import OrderedDict
from html import escape
from typing import Any

from app.bot.icons import (
    ICON_ACCOUNT,
    ICON_BALANCE,
    ICON_COIN,
    ICON_DEPOSIT,
    ICON_ID,
    ICON_NOTE,
    ICON_ORDERS,
)
from app.core.i18n import normalize_language
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
        self._user_cache: OrderedDict[int, tuple[float, dict[str, Any] | None]] = OrderedDict()
        self._cache_ttl: float = 30.0  # 30s cache for fast in-memory access during menu browsing
        self._lang_cache: dict[int, tuple[float, str]] = {}

    def invalidate_cache(self, tg_user_id: int) -> None:
        self._user_cache.pop(tg_user_id, None)
        self._lang_cache.pop(tg_user_id, None)

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
            self._user_cache[tg_user_id] = (time.monotonic(), result)
            if result.get("language"):
                self._lang_cache[tg_user_id] = (time.monotonic(), normalize_language(str(result["language"])))
            if row["is_new"]:
                cust = f" · @{escape(username)}" if username else ""
                full_name = escape(" ".join(filter(None, [first_name, last_name])) or "No name")
                self.notifier.in_background(
                    self.notifier.send_admin(
                        f"👤 <b>New Customer Joined</b>\n\n"
                        f"<b>Customer:</b> {full_name}{cust}\n"
                        f"<b>Customer ID:</b> <code>{tg_user_id}</code>",
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
            await conn.execute("SELECT set_config('app.wallet_reason',$1,true)", f"referral:{tg_user_id}")
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
        if await self.settings.flag("notify_user_referral"):
            self.notifier.in_background(
                self.notifier.send(
                    referrer_id,
                    f"<b>Referral reward</b>\n"
                    f"{joined_name} joined through your link.\n"
                    f"<code>+{reward_str}</code> added to your wallet.",
                )
            )
        return {"referrer_id": referrer_id, "amount": reward_amount}

    async def get(self, tg_user_id: int) -> dict[str, Any] | None:
        # Wallet, rank and ban state can change in another service or replica.
        # A profile cache must never authorize access or show an old balance.
        now = time.monotonic()
        async with self.db.connect() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE tg_user_id = $1", tg_user_id)
            res = dict(row) if row else None
            self._user_cache[tg_user_id] = (now, res)
            if len(self._user_cache) > 10000:
                self._user_cache.popitem(last=False)
            return res

    async def referral_summary(self, tg_user_id: int) -> dict[str, Any]:
        """The same rewarded-referral totals shown in the bot."""
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) AS total, COALESCE(SUM(amount), 0) AS earned "
                "FROM referral_rewards WHERE referrer_tg_id = $1", tg_user_id,
            )
        return {"total": row["total"], "earned": row["earned"]}

    async def get_language(self, tg_user_id: int) -> str:
        """Return the user's saved language, defaulting safely to English."""
        now = time.monotonic()
        cached = self._lang_cache.get(tg_user_id)
        if cached and now - cached[0] < self._cache_ttl:
            return cached[1]

        language = normalize_language(await self.get_raw_language(tg_user_id))
        self._lang_cache[tg_user_id] = (now, language)
        return language

    async def get_raw_language(self, tg_user_id: int) -> str | None:
        """Returns None if user has not yet explicitly selected a language."""
        cached_user = self._user_cache.get(tg_user_id)
        if (
            cached_user
            and cached_user[1]
            and time.monotonic() - cached_user[0] < self._cache_ttl
        ):
            val = cached_user[1].get("language")
            return val.strip().lower() if val else None
        async with self.db.connect() as conn:
            val = await conn.fetchval("SELECT language FROM users WHERE tg_user_id = $1", tg_user_id)
            return val.strip().lower() if val else None

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
            where_clauses.append(f"(u.username ILIKE ${len(params)} OR u.first_name ILIKE ${len(params)} OR u.last_name ILIKE ${len(params)} OR CAST(u.tg_user_id AS TEXT) LIKE ${len(params)})")
        if filter_type == "has_balance":
            where_clauses.append("u.balance > 0")
        elif filter_type == "banned":
            where_clauses.append("u.is_banned = 1")
        elif filter_type == "reseller":
            where_clauses.append("(LOWER(TRIM(COALESCE(u.rank, ''))) = 'reseller' OR u.tg_user_id IN (SELECT tg_user_id FROM reseller_api_keys))")

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        async with self.db.connect() as conn:
            total = await conn.fetchval(f"SELECT COUNT(*) FROM users u{where_sql}", *params)
            rows = await conn.fetch(
                f"""
                SELECT u.*,
                       k.key_prefix AS api_key_prefix,
                       k.is_active AS api_key_active,
                       k.last_used_at AS api_key_last_used_at
                FROM users u
                LEFT JOIN LATERAL (
                    SELECT key_prefix, is_active, last_used_at
                    FROM reseller_api_keys
                    WHERE tg_user_id = u.tg_user_id
                    ORDER BY created_at DESC
                    LIMIT 1
                ) k ON true
                {where_sql}
                ORDER BY u.id DESC
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
                """,
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
                    COUNT(CASE WHEN is_banned = 1 THEN 1 END) AS banned_count,
                    COUNT(CASE WHEN LOWER(TRIM(COALESCE(rank, ''))) = 'reseller' OR tg_user_id IN (SELECT tg_user_id FROM reseller_api_keys) THEN 1 END) AS reseller_count
                FROM users
                """
            )
        summary = {
            "total_users": int(summary_row["total_users"] or 0) if summary_row else 0,
            "total_balance": round(float(summary_row["total_balance"] or 0.0), 2) if summary_row else 0.0,
            "with_balance_count": int(summary_row["with_balance_count"] or 0) if summary_row else 0,
            "banned_count": int(summary_row["banned_count"] or 0) if summary_row else 0,
            "reseller_count": int(summary_row["reseller_count"] or 0) if summary_row else 0,
        }
        return [dict(row) for row in rows], total, summary

    async def adjust_balance(
        self, tg_user_id: int, delta: float, reason: str = "", *, notify: bool = False, operation_id: str | None = None
    ) -> dict[str, Any] | None:
        delta = money(delta)
        async with self.db.transaction() as conn:
            row = await conn.fetchrow("SELECT balance FROM users WHERE tg_user_id = $1 FOR UPDATE", tg_user_id)
            if not row:
                return None
            if operation_id:
                previous = await conn.fetchrow("SELECT * FROM admin_wallet_operations WHERE operation_id=$1", operation_id)
                if previous:
                    if previous['tg_user_id'] != tg_user_id or previous['delta'] != delta or previous['reason'] != reason:
                        raise InvalidInputError("This operation ID was used for a different adjustment.")
                    return dict(await conn.fetchrow("SELECT * FROM users WHERE tg_user_id=$1", tg_user_id))
                await conn.execute("INSERT INTO admin_wallet_operations(operation_id,tg_user_id,delta,reason) VALUES($1,$2,$3,$4)", operation_id, tg_user_id, delta, reason)
            new_balance = round(row["balance"] + delta, 4)
            if new_balance < 0:
                raise InvalidInputError("Adjustment would make the wallet negative.")
            await conn.execute("SELECT set_config('app.wallet_reason',$1,true)", f"admin_adjustment:{reason[:300]}")
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
        self.invalidate_cache(tg_user_id)
        if notify:
            self.notifier.in_background(self._notify_adjustment(tg_user_id, delta, user["balance"], reason))
        return dict(user)

    async def _notify_adjustment(self, tg_user_id: int, delta: float, balance: float, reason: str) -> None:
        symbol = escape(await self.settings.get("currency_symbol"))
        header = "<b>Wallet updated</b>"
        action_type = "Added" if delta >= 0 else "Deducted"
        await self.notifier.send(
            tg_user_id,
            f"{header}\n"
            f"{action_type}: <code>{abs(delta):.2f} {symbol}</code>\n"
            f"Balance: <code>{balance:.2f} {symbol}</code>\n"
            f"Reason: {escape(reason or 'Admin adjustment')}",
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
            self.invalidate_cache(tg_user_id)
            return bool(value)

    async def set_rank(self, tg_user_id: int, rank: str) -> str:
        """Update customer rank/role (Standard or Reseller)."""
        valid_ranks = {"Standard", "Reseller"}
        clean_rank = rank.strip().title()
        if clean_rank not in valid_ranks:
            clean_rank = "Standard"
        async with self.db.transaction() as conn:
            await conn.execute("UPDATE users SET rank = $1, updated_at = now() WHERE tg_user_id = $2", clean_rank, tg_user_id)
            await record(conn, "user_rank_updated", f"User #{tg_user_id} rank set to {clean_rank}")
        self.invalidate_cache(tg_user_id)
        return clean_rank

    async def set_language(self, tg_user_id: int, language: str) -> str:
        """Update customer preferred language ('en', 'bn')."""
        clean_lang = language.strip().lower()
        if clean_lang not in ("en", "bn"):
            clean_lang = "en"
        async with self.db.transaction() as conn:
            await conn.execute("UPDATE users SET language = $1, updated_at = now() WHERE tg_user_id = $2", clean_lang, tg_user_id)
        self.invalidate_cache(tg_user_id)
        self._lang_cache[tg_user_id] = (time.monotonic(), clean_lang)
        return clean_lang

    async def get_notification_preferences(self, tg_user_id: int) -> dict[str, bool]:
        """Only news is optional; payment results and deliveries are essential."""
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                "SELECT notify_orders, notify_deposits, notify_news FROM user_notification_preferences WHERE tg_user_id = $1",
                tg_user_id,
            )
            if not row:
                return {"notify_orders": True, "notify_deposits": True, "notify_news": True}
            return {
                "notify_orders": True,
                "notify_deposits": True,
                "notify_news": bool(row["notify_news"]),
            }

    async def toggle_notification_preference(self, tg_user_id: int, key: str) -> dict[str, bool]:
        """Toggle a specific notification preference and return updated map."""
        valid_keys = {"notify_news"}
        if key not in valid_keys:
            return await self.get_notification_preferences(tg_user_id)

        current = await self.get_notification_preferences(tg_user_id)
        new_val = not current.get(key, True)
        async with self.db.connect() as conn:
            await conn.execute(
                f"""
                INSERT INTO user_notification_preferences (tg_user_id, {key}, updated_at)
                VALUES ($1, $2, now())
                ON CONFLICT (tg_user_id) DO UPDATE SET {key} = $2, updated_at = now()
                """,
                tg_user_id,
                new_val,
            )
        current[key] = new_val
        return current

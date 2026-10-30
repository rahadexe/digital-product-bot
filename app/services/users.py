"""Customer accounts, referrals, wallet adjustments and bans."""

from __future__ import annotations

import time
from collections import OrderedDict
from html import escape
from typing import Any

from app.bot.formatting import format_dual_price
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
                self._lang_cache[tg_user_id] = (time.monotonic(), self._display_locale(str(result["language"])))
            if row["is_new"]:
                cust_uname = f"@{escape(username)}" if username else "None"
                full_name = escape(" ".join(filter(None, [first_name, last_name])) or "No name")
                self.notifier.in_background(
                    self.notifier.send_admin(
                        f"👤 <b>New Customer Joined</b>\n\n"
                        f"<blockquote>Name: <b>{full_name}</b>\n"
                        f"Username: {cust_uname}\n"
                        f"Customer ID: <code>{tg_user_id}</code></blockquote>",
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
            # 1. Anti-Sybil Defense: Check if the referred user has completed at least one approved deposit or purchase
            has_deposit = await conn.fetchval(
                "SELECT 1 FROM deposits WHERE tg_user_id = $1 AND status = 'approved' LIMIT 1",
                tg_user_id,
            )
            has_purchase = await conn.fetchval(
                "SELECT 1 FROM orders WHERE tg_user_id = $1 AND status = 'completed' LIMIT 1",
                tg_user_id,
            )
            if not has_deposit and not has_purchase:
                return None

            user_preview = await conn.fetchrow("SELECT referred_by, referral_rewarded FROM users WHERE tg_user_id = $1", tg_user_id)
            if not user_preview or not user_preview["referred_by"] or user_preview.get("referral_rewarded"):
                return None

            referrer_id = user_preview["referred_by"]
            if referrer_id == tg_user_id:
                return None

            # 2. Deadlock-free row locking: lock both users in deterministic sorted order
            locked_users = await conn.fetch(
                "SELECT * FROM users WHERE tg_user_id = ANY($1::bigint[]) ORDER BY tg_user_id FOR UPDATE",
                sorted([tg_user_id, referrer_id]),
            )
            user_map = {row["tg_user_id"]: row for row in locked_users}
            user = user_map.get(tg_user_id)
            referrer = user_map.get(referrer_id)

            if not user or not user["referred_by"] or user.get("referral_rewarded"):
                return None
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

        self.invalidate_cache(referrer_id)
        self.invalidate_cache(tg_user_id)

        raw_first_name = str(user.get("first_name") or "").strip()
        friend_name = escape(raw_first_name) if raw_first_name else "A friend"
        reward_str = format_dual_price(reward_amount, currency=await self.get_currency(referrer_id),
                                       usd_rate=await self.settings.number("usd_rate"))
        if await self.settings.flag("notify_user_referral"):
            self.notifier.in_background(
                self.notifier.send(
                    referrer_id,
                    "🎁 <b>Referral Reward!</b>\n\n"
                    f"Friend: <b>{friend_name}</b>\n"
                    f"Bonus: <code>+{reward_str}</code> added to your balance.",
                )
            )
        if getattr(self, "announcements", None):
            self.notifier.in_background(
                self.announcements.broadcast_referral_proof(
                    reward_str=reward_str,
                    first_name=referrer.get("first_name"),
                    last_name=referrer.get("last_name"),
                    username=referrer.get("username"),
                )
            )
        return {"referrer_id": referrer_id, "amount": reward_amount}

    async def get(self, tg_user_id: int) -> dict[str, Any] | None:
        now = time.monotonic()
        # Wallet credits, refunds and bans can be written by another worker.
        # Never serve a cached financial/account-access snapshot.

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
        """English copy with the current currency marker, shared across bot workers."""
        return "en" if await self.get_currency(tg_user_id) == "USD" else "en-BD"

    async def get_currency(self, tg_user_id: int) -> str:
        """Read the current preference; another worker may have handled the switch."""
        from app.services.currency import preferred_currency

        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                "SELECT currency, language FROM users WHERE tg_user_id = $1", tg_user_id
            )
        return preferred_currency(row)

    async def toggle_currency(self, tg_user_id: int) -> str:
        """Toggle currency between 'BDT' and 'USD'; returns the newly selected currency."""
        async with self.db.transaction() as conn:
            row = await conn.fetchrow(
                "SELECT currency, language FROM users WHERE tg_user_id = $1 FOR UPDATE", tg_user_id
            )
            if not row:
                raise InvalidInputError("User not found.")
            current = str(row["currency"] or "").strip().upper()
            if current not in {"BDT", "USD"}:
                current = "USD" if str(row["language"] or "").strip().lower() == "en" else "BDT"
            new_curr = "USD" if current == "BDT" else "BDT"
            new_lang = "en" if new_curr == "USD" else "en-BD"
            await conn.execute(
                "UPDATE users SET currency = $1, language = $2, updated_at = now() WHERE tg_user_id = $3",
                new_curr, new_lang, tg_user_id
            )
        self.invalidate_cache(tg_user_id)
        self._lang_cache[tg_user_id] = (time.monotonic(), new_lang)
        return new_curr

    async def set_currency(self, tg_user_id: int, currency: str) -> str:
        clean = "USD" if str(currency).strip().upper() == "USD" else "BDT"
        clean_lang = "en" if clean == "USD" else "en-BD"
        async with self.db.transaction() as conn:
            await conn.execute(
                "UPDATE users SET currency = $1, language = $2, updated_at = now() WHERE tg_user_id = $3",
                clean, clean_lang, tg_user_id
            )
        self.invalidate_cache(tg_user_id)
        self._lang_cache[tg_user_id] = (time.monotonic(), clean_lang)
        return clean

    @staticmethod
    def _display_locale(language: str) -> str:
        """All copy is English; the legacy Bangla preference only opts into BDT equivalents."""
        return "en-BD" if str(language).strip().lower() in {"bn", "en-bd"} else "en"

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

    async def total_count(self) -> int:
        """Return the total number of registered users."""
        async with self.db.connect() as conn:
            val = await conn.fetchval("SELECT COUNT(*) FROM users")
            return int(val or 0)

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
        currency = await self.get_currency(tg_user_id)
        rate = await self.settings.number("usd_rate")
        header = "💰 <b>Wallet Updated</b>"
        action_type = "Added" if delta >= 0 else "Deducted"
        delta_str = format_dual_price(abs(delta), usd_rate=rate, currency=currency)
        balance_str = format_dual_price(balance, usd_rate=rate, currency=currency)
        clean_reason = escape(reason.strip()) if reason and reason.strip() else "Admin adjustment"
        await self.notifier.send(
            tg_user_id,
            f"{header}\n\n"
            f"{action_type}: <code>{delta_str}</code>\n"
            f"Current Balance: <code>{balance_str}</code>\n"
            f"Reason: <i>{clean_reason}</i>",
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
            if clean_rank != "Reseller":
                await conn.execute("UPDATE reseller_api_keys SET is_active = 0, updated_at = now() WHERE tg_user_id = $1", tg_user_id)
            await record(conn, "user_rank_updated", f"User #{tg_user_id} rank set to {clean_rank}")
        self.invalidate_cache(tg_user_id)
        return clean_rank

    async def set_language(self, tg_user_id: int, language: str) -> str:
        """Keep legacy callers compatible while enforcing the English-only bot."""
        clean_lang = "en-BD" if str(language).strip().lower() in {"bn", "en-bd", "bdt"} else "en"
        clean_curr = "BDT" if clean_lang == "en-BD" else "USD"
        async with self.db.transaction() as conn:
            await conn.execute("UPDATE users SET language = $1, currency = $2, updated_at = now() WHERE tg_user_id = $3", clean_lang, clean_curr, tg_user_id)
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

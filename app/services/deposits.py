"""Manual deposits: payment methods, quotes, requests and admin review.

The bot and admin console use the same quote rules, and each
request stores the exchange rate and payable amount the customer was shown.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from html import escape
from typing import Any

import asyncpg
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.customer_copy import wallet_updated
from app.bot.icons import (
    ICON_ACCOUNT,
    ICON_BALANCE,
    ICON_CHECK,
    ICON_COIN,
    ICON_DEPOSIT,
    ICON_ID,
    ICON_KEY,
    ICON_MONEY,
    ICON_NOTE,
    ICON_WARNING,
    Icons,
)
from app.core.config import get_settings
from app.core.identifiers import format_deposit_id
from app.core.money import money
from app.db import Database, affected
from app.services.admin_jobs import enqueue as enqueue_admin_job
from app.services.audit import record
from app.services.errors import InvalidInputError
from app.services.notifications import Notifier
from app.services.settings import SettingsService

TRANSACTION_ID = re.compile(r"[A-Za-z0-9_\-]{5,80}")
CUSTOMER_DEPOSIT_COLUMNS = (
    "id, method_name, amount, pay_amount, rate_to_currency, transaction_id, status, admin_note, created_at, reviewed_at"
)
METHOD_FIELDS = (
    "name",
    "account_info",
    "account_type",
    "instructions",
    "min_deposit",
    "rate_to_currency",
    "is_active",
    "sort_order",
    "auto_verify",
    "auto_verify_network",
    "custom_emoji_id",
)


class DuplicateTransactionError(InvalidInputError):
    pass


class PendingDepositError(InvalidInputError):
    pass


def is_binance_pay_method(method: Any) -> bool:
    """USD wallet and Binance USDT are credited 1:1 for every crypto deposit method."""
    return (
        method.get("auto_verify") in {"binance", "binance_pay"}
        or method.get("account_type") == "crypto"
        or "binance" in (method.get("name") or "").lower()
    )

class DepositService:
    CACHE_SECONDS = 60.0

    def __init__(self, db: Database, settings: SettingsService, notifier: Notifier):
        self.db = db
        self.settings = settings
        self.notifier = notifier
        self._methods_cache: tuple[float, list[dict[str, Any]]] | None = None

    def invalidate_methods_cache(self) -> None:
        self._methods_cache = None

    async def verification_failures(self, tg_user_id: int, *, record_failure: bool = False) -> list[float]:
        async with self.db.connect() as conn:
            if record_failure:
                row = await conn.fetchrow(
                    "INSERT INTO verification_limits(tg_user_id,failures) VALUES($1,1) ON CONFLICT(tg_user_id) "
                    "DO UPDATE SET failures=CASE WHEN verification_limits.expires_at<=now() THEN 1 ELSE verification_limits.failures+1 END, "
                    "window_started=CASE WHEN verification_limits.expires_at<=now() THEN now() ELSE verification_limits.window_started END, "
                    "expires_at=CASE WHEN verification_limits.expires_at<=now() THEN now()+interval '10 minutes' ELSE verification_limits.expires_at END "
                    "RETURNING failures,window_started", tg_user_id,
                )
            else:
                row = await conn.fetchrow(
                    "SELECT failures,window_started FROM verification_limits WHERE tg_user_id=$1 AND expires_at>now()", tg_user_id
                )
        return [row['window_started'].timestamp()] * min(row['failures'], 3) if row else []

    async def clear_verification_failures(self, tg_user_id: int) -> None:
        async with self.db.connect() as conn:
            await conn.execute("DELETE FROM verification_limits WHERE tg_user_id=$1", tg_user_id)

    # --- Payment methods ---
    async def methods(self, active_only: bool = True) -> list[dict[str, Any]]:
        now = time.monotonic()
        if active_only and self._methods_cache and now - self._methods_cache[0] < self.CACHE_SECONDS:
            return [dict(row) for row in self._methods_cache[1]]
        query = (
            "SELECT dm.*, EXISTS (SELECT 1 FROM binance_method_credentials bc WHERE bc.method_id = dm.id) AS has_api_credentials "
            "FROM deposit_methods dm"
            + (" WHERE dm.is_active = 1" if active_only else "")
            + " ORDER BY dm.sort_order, dm.id"
        )
        async with self.db.connect() as conn:
            rows = [dict(row) for row in await conn.fetch(query)]
        if active_only:
            self._methods_cache = (now, rows)
        return [dict(row) for row in rows]

    async def get_method(self, method_id: int) -> dict[str, Any] | None:
        query = (
            "SELECT dm.*, EXISTS (SELECT 1 FROM binance_method_credentials bc WHERE bc.method_id = dm.id) AS has_api_credentials "
            "FROM deposit_methods dm WHERE dm.id = $1"
        )
        async with self.db.connect() as conn:
            row = await conn.fetchrow(query, method_id)
        return dict(row) if row else None

    async def create_method(
        self,
        name: str,
        account_info: str,
        instructions: str = "",
        min_deposit: float = 1.0,
        rate: float = 1.0,
        sort_order: int = 0,
        is_active: int = 1,
        auto_verify: str = "none",
        auto_verify_network: str = "",
        custom_emoji_id: str | None = None,
        account_type: str = "personal",
    ) -> int:
        async with self.db.transaction() as conn:
            method_id = await conn.fetchval(
                """
                INSERT INTO deposit_methods (name, account_info, instructions, min_deposit, rate_to_currency,
                                             sort_order, is_active, auto_verify, auto_verify_network, custom_emoji_id, account_type)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) RETURNING id
                """,
                name,
                account_info,
                instructions,
                money(min_deposit, positive=True),
                rate,
                sort_order,
                is_active,
                auto_verify,
                auto_verify_network,
                custom_emoji_id,
                account_type,
            )
            await record(conn, "deposit_method_created", f"Method #{method_id}: {name}")
        self.invalidate_methods_cache()
        return method_id

    async def update_method(self, method_id: int, **fields: Any) -> bool:
        updates = {key: value for key, value in fields.items() if key in METHOD_FIELDS}
        if not updates:
            return False
        columns = ", ".join(f"{key} = ${index}" for index, key in enumerate(updates, start=1))
        async with self.db.transaction() as conn:
            status = await conn.execute(
                f"UPDATE deposit_methods SET {columns} WHERE id = ${len(updates) + 1}", *updates.values(), method_id
            )
            if affected(status):
                # Payment destinations are what attackers change; keep a trail of every edit.
                await record(conn, "deposit_method_updated", f"Method #{method_id}: {', '.join(sorted(updates))}")
        if affected(status):
            self.invalidate_methods_cache()
        return bool(affected(status))

    async def get_or_create_binance_method(self) -> dict[str, Any]:
        settings = await self.settings.values()
        is_active = 1 if settings.get("binance_enabled") == "1" else 0
        pay_id = settings.get("binance_pay_id", "12345678")
        instructions = settings.get("binance_pay_instructions", "")
        min_deposit = float(settings.get("binance_pay_min", "100"))
        rate = float(settings.get("binance_pay_rate", "125"))

        async with self.db.transaction() as conn:
            await conn.execute("SELECT pg_advisory_xact_lock(7302114552)")
            row = await conn.fetchrow(
                "SELECT * FROM deposit_methods WHERE auto_verify = 'binance_pay' ORDER BY id LIMIT 1 FOR UPDATE"
            )
            if row:
                await conn.execute(
                    """
                    UPDATE deposit_methods
                    SET name = 'Binance', account_info = $1, instructions = $2, min_deposit = $3, rate_to_currency = $4,
                        is_active = $5, auto_verify = 'binance_pay', auto_verify_network = 'Binance ID'
                    WHERE id = $6
                    """,
                    pay_id,
                    instructions,
                    min_deposit,
                    rate,
                    is_active,
                    row["id"],
                )
                updated = await conn.fetchrow("SELECT * FROM deposit_methods WHERE id = $1", row["id"])
                return dict(updated)
            else:
                method_id = await conn.fetchval(
                    """
                    INSERT INTO deposit_methods (name, account_info, instructions, min_deposit, rate_to_currency,
                                                 sort_order, is_active, auto_verify, auto_verify_network, custom_emoji_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING id
                    """,
                    "Binance",
                    pay_id,
                    instructions,
                    money(min_deposit, positive=True),
                    rate,
                    -1,
                    is_active,
                    "binance_pay",
                    "Binance ID",
                    "5348212415077064131",
                )
                created = await conn.fetchrow("SELECT * FROM deposit_methods WHERE id = $1", method_id)
                return dict(created)

    async def delete_method(self, method_id: int) -> bool:
        """Remove a method for good. Deposits made with it stay, named as they were when they were made."""
        async with self.db.transaction() as conn:
            row = await conn.fetchrow("SELECT name, auto_verify FROM deposit_methods WHERE id = $1 FOR UPDATE", method_id)
            if row is None:
                return False
            if await conn.fetchval("SELECT 1 FROM deposits WHERE method_id=$1 AND status='pending' LIMIT 1", method_id):
                raise InvalidInputError("Review pending deposits before deleting this payment method.")
            # Every deposit already carries the method's name, so dropping the link loses nothing shown.
            await conn.execute("UPDATE deposits SET method_id = NULL WHERE method_id = $1", method_id)
            await conn.execute("DELETE FROM deposit_methods WHERE id = $1", method_id)
            await record(conn, "deposit_method_deleted", f"Method #{method_id}: {row['name']}")
        self.invalidate_methods_cache()
        return True

    async def archive_method(self, method_id: int) -> None:
        async with self.db.transaction() as conn:
            if affected(await conn.execute("UPDATE deposit_methods SET is_active = 0 WHERE id = $1", method_id)):
                await record(conn, "deposit_method_archived", f"Method #{method_id}")

    # --- Requests ---
    async def _quote(self, method: Any, amount: float, values: dict[str, str] | None = None) -> dict[str, Any]:
        values = values if values is not None else await self.settings.values()
        rate = 1.0 if is_binance_pay_method(method) else float(values.get("usd_rate") or 125)
        is_crypto = is_binance_pay_method(method)
        pay_amount = round(amount if is_crypto else amount * rate, 4)
        minimum = float(method["min_deposit"] or 0.0)
        paid_for_minimum = amount if is_crypto else pay_amount
        if paid_for_minimum < minimum:
            currency = "USDT" if is_crypto else "BDT"
            raise InvalidInputError(f"The minimum payment for this method is {currency}{minimum:.2f}.")
        limit = float(values.get("max_deposit_limit") or 0.0)
        if limit and amount > limit:
            raise InvalidInputError(f"The maximum wallet credit is ${limit:.2f}. Contact support for larger payments.")
        return {
            "method_id": method["id"],
            "method_name": method["name"],
            "account_info": method["account_info"],
            "account_type": method.get("account_type") or "personal",
            "instructions": method["instructions"] or "",
            "amount": amount,
            "rate": rate,
            "pay_amount": pay_amount,
            "paid_currency": values.get("binance_coin", "USDT") if is_crypto else "BDT",
        }

    async def quote(self, method_id: int, amount: Any) -> dict[str, Any]:
        """Validate an amount for a method and return what the customer must pay."""
        try:
            amount = money(amount, positive=True)
        except (TypeError, ValueError):
            raise InvalidInputError("Enter a valid amount, for example 10 or 25.50.") from None
        async with self.db.connect() as conn:
            method = await conn.fetchrow("SELECT * FROM deposit_methods WHERE id = $1 AND is_active = 1", method_id)
        if not method:
            raise InvalidInputError("Payment method is no longer available.")
        return await self._quote(method, amount)

    async def create_request(
        self,
        tg_user_id: int,
        method_id: int,
        amount: float,
        transaction_id: str,
        *,
        pay_amount: float | None = None,
        quoted_rate: float | None = None,
        admin_note: str = "",
        verification_id: str | None = None,
        notify_admin: bool = True,
    ) -> int:
        paused = await self.settings.paused_message()
        if paused:
            raise InvalidInputError(paused)
        amount = money(amount, positive=True)
        clean_tx = str(transaction_id).strip()
        if not TRANSACTION_ID.fullmatch(clean_tx):
            raise InvalidInputError("Invalid transaction ID.")
        values = await self.settings.values()
        try:
            async with self.db.transaction() as conn:
                user = await conn.fetchrow("SELECT id, username, is_banned FROM users WHERE tg_user_id = $1", tg_user_id)
                if not user or user["is_banned"]:
                    raise InvalidInputError("Account unavailable or suspended.")
                method = await conn.fetchrow("SELECT * FROM deposit_methods WHERE id = $1 AND is_active = 1", method_id)
                if not method:
                    raise InvalidInputError("Payment method is no longer available.")
                if pay_amount is not None:
                    actual_pay_amount = money(pay_amount, positive=True)
                    is_crypto = is_binance_pay_method(method)
                    rate = 1.0 if is_crypto else float(quoted_rate or values.get("usd_rate") or 125)
                    actual_amount = amount
                    expected_amount = round(actual_pay_amount if is_crypto else actual_pay_amount / rate, 4)
                    if abs(expected_amount - actual_amount) > 0.001:
                        raise InvalidInputError("The payment amount and USD wallet credit do not match the current rate.")
                    min_dep = float(method["min_deposit"] or 0.0)
                    minimum_paid = actual_amount if is_crypto else actual_pay_amount
                    if minimum_paid < min_dep:
                        curr = "USDT" if is_crypto else "BDT"
                        raise InvalidInputError(f"The minimum payment for this method is {curr}{min_dep:g}.")
                    limit = float(values.get("max_deposit_limit") or 0.0)
                    if limit and actual_amount > limit:
                        raise InvalidInputError(f"The maximum wallet credit is ${limit:g}. Contact support for larger payments.")
                    quote = {
                        "method_id": method["id"],
                        "method_name": method["name"],
                        "account_info": method["account_info"],
                        "account_type": method.get("account_type") or "personal",
                        "instructions": method["instructions"] or "",
                        "amount": actual_amount,
                        "rate": rate,
                        "pay_amount": actual_pay_amount,
                        "paid_currency": values.get("binance_coin", "USDT") if is_crypto else "BDT",
                    }
                else:
                    quote = await self._quote(method, amount, values)
                    if quoted_rate is not None and abs(quote["rate"] - quoted_rate) > 1e-9:
                        raise InvalidInputError("The payment rate changed. Please start the deposit again.")
                    actual_amount = amount
                    actual_pay_amount = quote["pay_amount"]
                    rate = quote["rate"]

                deposit_id = await conn.fetchval(
                    """
                    INSERT INTO deposits (user_id, tg_user_id, method_id, method_name, amount, transaction_id,
                                          status, rate_to_currency, pay_amount, admin_note, paid_currency)
                    VALUES ($1, $2, $3, $4, $5, $6, 'pending', $7, $8, $9, $10) RETURNING id
                    """,
                    user["id"],
                    tg_user_id,
                    method_id,
                    method["name"],
                    actual_amount,
                    clean_tx,
                    quote["rate"],
                    quote["pay_amount"],
                    admin_note or "",
                    quote["paid_currency"],
                )
                await enqueue_admin_job(conn, 'deposit', deposit_id, dict(deposit_id=deposit_id, tg_user_id=tg_user_id, username=user['username'], quote=quote, transaction_id=clean_tx, admin_note=admin_note))
                if not notify_admin:
                    # Give automatic verification time to finish. If the process
                    # dies between creation and verification, an owner still hears.
                    await conn.execute("UPDATE admin_notification_jobs SET next_attempt=now()+interval '60 seconds' WHERE event_key=$1", f'deposit:{deposit_id}')
                if verification_id is not None:
                    await conn.execute(
                        "INSERT INTO payment_verification_attempts(deposit_id,provider,verify_id,status) VALUES($1,'zinipay',$2,'reserved')",
                        deposit_id, verification_id,
                    )
        except asyncpg.UniqueViolationError as exc:
            if exc.constraint_name == "deposit_one_pending":
                raise PendingDepositError("You already have a deposit waiting for review.") from exc
            raise DuplicateTransactionError("This transaction ID has already been submitted.") from exc

        # An automatic verification calls this first and credits the wallet a moment
        # later, so alerting here put "New Deposit Request — Approve / Reject" in front
        # of an owner for a deposit that was already approved by the time they read it.
        # Those paths alert from alert_admin_needs_review instead, once it is clear a
        # person is actually needed.
        # Notification is durable and was committed with the deposit.
        return deposit_id

    async def alert_admin_needs_review(self, deposit_id: int, note: str = "") -> None:
        """Automatic verification has finished trying: now it is somebody's job."""
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                "SELECT d.*, u.username FROM deposits d LEFT JOIN users u ON u.id = d.user_id "
                "WHERE d.id = $1 AND d.status = 'pending'", deposit_id)
        if not row:
            return
        quote = {
            "method_name": row["method_name"],
            "amount": float(row["amount"]),
            "pay_amount": float(row["pay_amount"] or row["amount"]),
            "rate": float(row["rate_to_currency"] or 1),
        }
        async with self.db.connect() as conn:
            await enqueue_admin_job(conn, 'deposit', deposit_id, dict(deposit_id=deposit_id, tg_user_id=row['tg_user_id'], username=row['username'], quote=quote, transaction_id=row['transaction_id'], admin_note=note or row['admin_note'] or ''))
            await conn.execute("UPDATE admin_notification_jobs SET next_attempt=now(),payload=jsonb_set(payload,'{admin_note}',to_jsonb($2::text)) WHERE event_key=$1 AND status='pending'", f'deposit:{deposit_id}', note or row['admin_note'] or '')

    async def _notify_new_request(
        self,
        deposit_id: int,
        tg_user_id: int,
        username: str | None,
        quote: dict[str, Any],
        transaction_id: str,
        admin_note: str = "",
    ) -> None:
        customer = f"@{escape(username)}" if username else "No username"
        payable = f"\n<b>Customer pays:</b> {quote['pay_amount']:.2f} {quote['paid_currency']} (wallet credit ${quote['amount']:.2f})"
        note_line = f"\n⚠️ <b>Note:</b> <i>{escape(admin_note)}</i>" if admin_note else ""

        # Reviewing a deposit is the most time-critical thing an operator does:
        # a customer has already sent money and is waiting. Offer the decision
        # here rather than only a link that costs a browser and a login.
        console = get_settings().console_url
        rows = [[
            InlineKeyboardButton(
                text="Approve",
                callback_data=f"adm_dep_ask_approve_{deposit_id}",
            ),
            InlineKeyboardButton(
                text="Reject",
                callback_data=f"adm_dep_ask_reject_{deposit_id}",
            ),
        ]]
        if console:
            rows.append([
                InlineKeyboardButton(
                    text="Open in Console",
                    url=f"{console}/#deposits",
                )
            ])
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

        await self.notifier.send_admin(
            f"⏳ <b>New Deposit Request · {format_deposit_id(deposit_id)}</b>\n\n"
            f"<b>Customer:</b> {customer}\n"
            f"<b>Customer ID:</b> <code>{tg_user_id}</code>\n"
            f"<b>Method:</b> {escape(quote['method_name'])}\n"
            f"<b>Wallet credit:</b> <code>${quote['amount']:.2f}</code>\n"
            f"{payable}\n"
            f"<b>TrxID:</b> <code>{escape(transaction_id)}</code>"
            f"{note_line}",
            event="deposit",
            keyboard=keyboard,
        )

    async def _notify_customer(
        self, tg_user_id: int, text_for_symbol: Callable[[str], str], keyboard: InlineKeyboardMarkup | None = None
    ) -> None:
        symbol = escape(await self.settings.get("currency_symbol"))
        await self.notifier.send(tg_user_id, text_for_symbol(symbol), keyboard=keyboard)

    async def pending_for(self, tg_user_id: int) -> dict[str, Any] | None:
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                f"SELECT {CUSTOMER_DEPOSIT_COLUMNS} FROM deposits WHERE tg_user_id = $1 AND status = 'pending' "
                "ORDER BY id DESC LIMIT 1",
                tg_user_id,
            )
            return dict(row) if row else None

    async def history(self, tg_user_id: int, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        """A customer's own deposits, newest first, with what they were asked to pay and the review outcome."""
        async with self.db.connect() as conn:
            rows = await conn.fetch(
                f"SELECT {CUSTOMER_DEPOSIT_COLUMNS} FROM deposits WHERE tg_user_id = $1 ORDER BY id DESC LIMIT $2 OFFSET $3",
                tg_user_id,
                limit,
                offset,
            )
        return [dict(row) for row in rows]

    async def get_for_customer(self, tg_user_id: int, deposit_id: int) -> dict[str, Any] | None:
        """Fetch a specific deposit belonging to a customer."""
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                f"SELECT {CUSTOMER_DEPOSIT_COLUMNS} FROM deposits WHERE tg_user_id = $1 AND id = $2",
                tg_user_id,
                deposit_id,
            )
            return dict(row) if row else None

    async def count_for_user(self, tg_user_id: int) -> int:
        """Total deposit requests submitted by a user."""
        async with self.db.connect() as conn:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM deposits WHERE tg_user_id = $1",
                tg_user_id,
            ) or 0

    async def find_by_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM deposits WHERE lower(btrim(transaction_id)) = lower(btrim($1)) LIMIT 1", transaction_id
            )
            return dict(row) if row else None

    async def record_received_transaction(
        self,
        transaction_id: str,
        amount: float,
        provider: str = "bKash",
        sender_number: str = "",
        raw_message: str = "",
    ) -> dict[str, Any] | None:
        """Store an incoming payment statement received via SMS forwarder or statement webhook."""
        clean_tx = str(transaction_id).strip()
        amt = money(amount, positive=True)
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO received_transactions (transaction_id, amount, provider, sender_number, raw_message, status)
                VALUES ($1, $2, $3, $4, $5, 'unused')
                ON CONFLICT (lower(btrim(transaction_id))) DO NOTHING
                RETURNING *
                """,
                clean_tx,
                amt,
                provider,
                sender_number,
                raw_message,
            )
            return dict(row) if row else None

    async def get_unused_received_transaction(self, transaction_id: str) -> dict[str, Any] | None:
        """Retrieve an unconsumed payment statement for this transaction ID."""
        clean_tx = str(transaction_id).strip()
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM received_transactions
                WHERE lower(btrim(transaction_id)) = lower(btrim($1)) AND status = 'unused'
                LIMIT 1
                """,
                clean_tx,
            )
            return dict(row) if row else None

    async def claim_received_transaction(
        self, transaction_id: str, tg_user_id: int, deposit_id: int
    ) -> bool:
        """Atomically lock and mark a received statement as used."""
        clean_tx = str(transaction_id).strip()
        async with self.db.connect() as conn:
            updated = await conn.fetchval(
                """
                UPDATE received_transactions
                SET status = 'used', used_by_tg_id = $1, used_at = now(), deposit_id = $2
                WHERE lower(btrim(transaction_id)) = lower(btrim($3)) AND status = 'unused'
                RETURNING id
                """,
                tg_user_id,
                deposit_id,
                clean_tx,
            )
            return bool(updated)

    async def list(self, status: str | None = None, limit: int = 50, offset: int = 0, search: str | None = None) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
        where_clauses: list[str] = []
        params: list[Any] = []
        if status:
            params.append(status)
            where_clauses.append(f"d.status = ${len(params)}")
        if search and search.strip():
            raw = search.strip()
            clean = raw.lstrip("#").lstrip("D").lstrip("d")
            params.append(f"%{raw}%")
            idx = len(params)
            if clean.isdigit():
                params.append(int(clean))
                num_idx = len(params)
                where_clauses.append(f"(d.transaction_id ILIKE ${idx} OR u.username ILIKE ${idx} OR u.first_name ILIKE ${idx} OR d.id = ${num_idx} OR d.tg_user_id = ${num_idx})")
            else:
                where_clauses.append(f"(d.transaction_id ILIKE ${idx} OR u.username ILIKE ${idx} OR u.first_name ILIKE ${idx} OR d.method_name ILIKE ${idx})")

        where = f" AND {' AND '.join(where_clauses)}" if where_clauses else ""
        async with self.db.connect() as conn:
            total = await conn.fetchval(
                f"""
                SELECT COUNT(*) FROM deposits d
                LEFT JOIN users u ON u.id = d.user_id
                WHERE 1=1{where}
                """,
                *params,
            ) or 0
            rows = await conn.fetch(
                f"""
                SELECT d.*, u.username, u.first_name, COALESCE(m.auto_verify, 'none') AS auto_verify
                FROM deposits d LEFT JOIN users u ON u.id = d.user_id LEFT JOIN deposit_methods m ON m.id = d.method_id
                WHERE 1=1{where}
                ORDER BY d.id DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
                """,
                *params,
                limit,
                offset,
            )
            summary_row = await conn.fetchrow(
                """
                SELECT 
                    COALESCE(SUM(CASE WHEN status = 'approved' THEN amount ELSE 0 END), 0)::float AS total_completed_amount,
                    COUNT(CASE WHEN status = 'pending' THEN 1 END)::int AS pending_count,
                    COALESCE(SUM(CASE WHEN status = 'pending' THEN amount ELSE 0 END), 0)::float AS pending_amount,
                    COALESCE(SUM(CASE WHEN status = 'approved' AND created_at >= CURRENT_DATE THEN amount ELSE 0 END), 0)::float AS today_amount
                FROM deposits
                """
            )
        summary = {
            "total_completed_amount": round(float(summary_row["total_completed_amount"] or 0.0), 2) if summary_row else 0.0,
            "pending_count": int(summary_row["pending_count"] or 0) if summary_row else 0,
            "pending_amount": round(float(summary_row["pending_amount"] or 0.0), 2) if summary_row else 0.0,
            "today_amount": round(float(summary_row["today_amount"] or 0.0), 2) if summary_row else 0.0,
        }
        return [dict(row) for row in rows], total, summary

    async def cancel_awaiting_sms(self, deposit_id: int, tg_user_id: int) -> bool:
        """The customer says they mistyped the TrxID, so stop waiting for a receipt that will never come.

        Narrow on purpose: only their own deposit, only while it is still pending, and only
        one the bot filed because the gateway had not seen the receipt yet. A deposit an
        operator is in the middle of approving is not reachable from here.
        """
        async with self.db.transaction() as conn:
            cancelled = await conn.fetchval(
                "UPDATE deposits SET status='rejected', admin_note=$3, reviewed_at=now() "
                "WHERE id=$1 AND tg_user_id=$2 AND status='pending' RETURNING id",
                deposit_id, tg_user_id, "Cancelled by the customer to correct the transaction ID.",
            )
            if cancelled:
                await conn.execute(
                    "UPDATE payment_verification_attempts SET status='review',"
                    "note='Cancelled by the customer to correct the transaction ID.',updated_at=now() "
                    "WHERE deposit_id=$1", deposit_id,
                )
                await record(conn, "deposit_cancelled_by_customer",
                             f"Deposit #{deposit_id}: cancelled by the customer to correct the TrxID.")
        return bool(cancelled)

    async def approve(
        self, deposit_id: int, admin_note: str = "", notify_customer: bool = True
    ) -> tuple[bool, str, dict[str, Any] | None]:
        async with self.db.transaction() as conn:
            deposit = await conn.fetchrow("SELECT * FROM deposits WHERE id = $1 FOR UPDATE", deposit_id)
            if not deposit:
                return False, "Deposit record not found.", None
            if deposit["status"] != "pending":
                return False, f"Deposit already marked as {deposit['status']}.", None
            if await conn.fetchval(
                "SELECT 1 FROM payment_verification_attempts WHERE deposit_id=$1 AND status IN ('reserved','confirming')", deposit_id
            ):
                return False, "Automatic verification is still running. Please wait before reviewing.", None
            if await conn.fetchval(
                "SELECT 1 FROM deposits WHERE id <> $1 AND status = 'approved' "
                "AND lower(btrim(transaction_id)) = lower(btrim($2))",
                deposit_id,
                deposit["transaction_id"],
            ):
                return False, "This transaction has already been credited.", None
            amount = money(deposit["amount"], positive=True)
            await conn.execute("SELECT set_config('app.wallet_reason',$1,true)", f"deposit:{deposit_id}")
            new_balance = await conn.fetchval(
                "UPDATE users SET balance = balance + $1, updated_at = now() WHERE tg_user_id = $2 RETURNING balance",
                amount,
                deposit["tg_user_id"],
            )
            await conn.execute(
                "UPDATE deposits SET status = 'approved', admin_note = $1, reviewed_at = now() WHERE id = $2",
                admin_note,
                deposit_id,
            )
            await record(
                conn, "approve_deposit", f"Approved Deposit #{deposit_id} of {amount:.2f} for user {deposit['tg_user_id']}"
            )

        details = {
            "tg_user_id": deposit["tg_user_id"],
            "amount": amount,
            "new_balance": new_balance if new_balance is not None else amount,
            "method_name": deposit["method_name"],
        }
        if notify_customer:
            self.notifier.in_background(
                self._notify_customer(
                    deposit["tg_user_id"],
                    lambda symbol: (
                        wallet_updated(amount, details["new_balance"], symbol, deposit_id)
                    ),
                )
            )
        return True, "Deposit approved and user credited.", details

    async def reject(
        self, deposit_id: int, admin_note: str = "Transaction could not be verified."
    ) -> tuple[bool, str, dict[str, Any] | None]:
        async with self.db.transaction() as conn:
            deposit = await conn.fetchrow("SELECT * FROM deposits WHERE id = $1 FOR UPDATE", deposit_id)
            if not deposit:
                return False, "Deposit record not found.", None
            if deposit["status"] != "pending":
                return False, f"Deposit already marked as {deposit['status']}.", None
            if await conn.fetchval(
                "SELECT 1 FROM payment_verification_attempts WHERE deposit_id=$1 AND status IN ('reserved','confirming')", deposit_id
            ):
                return False, "Automatic verification is still running. Please wait before reviewing.", None
            await conn.execute(
                "UPDATE deposits SET status = 'rejected', admin_note = $1, reviewed_at = now() WHERE id = $2",
                admin_note,
                deposit_id,
            )
            await record(
                conn, "reject_deposit", f"Rejected Deposit #{deposit_id} for user {deposit['tg_user_id']}. Reason: {admin_note}"
            )

        amount = deposit["amount"]
        method_name = escape(deposit.get("method_name") or "Deposit")
        trx_id = escape(deposit.get("transaction_id") or "")
        tg_user_id = deposit["tg_user_id"]

        async with self.db.connect() as conn:
            user_row = await conn.fetchrow("SELECT username, first_name FROM users WHERE tg_user_id = $1", tg_user_id)
        u_handle = f"@{escape(user_row['username'])}" if user_row and user_row.get("username") else (escape(user_row["first_name"]) if user_row and user_row.get("first_name") else "Customer")

        support_user = await self.settings.get("support_username")
        support_kb = None
        if support_user:
            clean_sup = support_user.lstrip("@")
            support_kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Contact Support", url=f"https://t.me/{clean_sup}")
            ]])
        else:
            support_kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Contact Support", callback_data="open_support")
            ]])

        self.notifier.in_background(
            self._notify_customer(
                tg_user_id,
                lambda symbol: (
                    "⚠️ <b>Deposit Not Approved</b>\n\n"
                    f"Method: <b>{method_name}</b>\n"
                    f"Amount: <code>{amount:g} {symbol}</code>\n"
                    + (f"TrxID: <code>{trx_id}</code>\n" if trx_id else "")
                    + f"Reason: <i>{escape(admin_note) or 'Payment could not be verified.'}</i>"
                ),
                keyboard=support_kb,
            )
        )
        return True, "Deposit rejected.", {"tg_user_id": deposit["tg_user_id"], "amount": deposit["amount"], "reason": admin_note}

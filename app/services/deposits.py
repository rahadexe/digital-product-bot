"""Manual deposits: payment methods, quotes, requests and admin review.

The bot, the Mini App and the admin console all use the same quote rules, and each
request stores the exchange rate and payable amount the customer was shown.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from html import escape
from typing import Any

import asyncpg
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

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
from app.core.money import money
from app.db import Database, affected
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


class DepositService:
    def __init__(self, db: Database, settings: SettingsService, notifier: Notifier):
        self.db = db
        self.settings = settings
        self.notifier = notifier

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
        query = "SELECT * FROM deposit_methods" + (" WHERE is_active = 1" if active_only else "") + " ORDER BY sort_order, id"
        async with self.db.connect() as conn:
            return [dict(row) for row in await conn.fetch(query)]

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
                        is_active = $5, auto_verify = 'binance_pay', auto_verify_network = 'Binance ID',
                        custom_emoji_id = COALESCE(custom_emoji_id, '5348212415077064131')
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
            if row["auto_verify"] == "binance_pay":
                raise InvalidInputError("System gateway methods cannot be deleted.")
            if await conn.fetchval("SELECT 1 FROM deposits WHERE method_id=$1 AND status='pending' LIMIT 1", method_id):
                raise InvalidInputError("Review pending deposits before deleting this payment method.")
            # Every deposit already carries the method's name, so dropping the link loses nothing shown.
            await conn.execute("UPDATE deposits SET method_id = NULL WHERE method_id = $1", method_id)
            await conn.execute("DELETE FROM deposit_methods WHERE id = $1", method_id)
            await record(conn, "deposit_method_deleted", f"Method #{method_id}: {row['name']}")
        return True

    async def archive_method(self, method_id: int) -> None:
        async with self.db.transaction() as conn:
            if affected(await conn.execute("UPDATE deposit_methods SET is_active = 0 WHERE id = $1", method_id)):
                await record(conn, "deposit_method_archived", f"Method #{method_id}")

    # --- Requests ---
    async def _quote(self, method: Any, amount: float, values: dict[str, str] | None = None) -> dict[str, Any]:
        values = values if values is not None else await self.settings.values()
        symbol = values["currency_symbol"]
        limit = float(values["max_deposit_limit"])
        rate = float(method["rate_to_currency"])
        is_pay = method.get("auto_verify") == "binance_pay"
        minimum = method["min_deposit"] * rate if is_pay else method["min_deposit"]
        if amount < minimum:
            raise InvalidInputError(f"The minimum deposit for this method is {symbol}{minimum:.2f}.")
        if amount > limit:
            raise InvalidInputError(f"The maximum single deposit is {symbol}{limit:.2f}. Contact support for larger payments.")
        return {
            "method_id": method["id"],
            "method_name": method["name"],
            "account_info": method["account_info"],
            "account_type": method.get("account_type") or "personal",
            "instructions": method["instructions"] or "",
            "amount": amount,
            "rate": rate,
            "pay_amount": round(amount / rate if is_pay else amount * rate, 4),
            "paid_currency": values.get("binance_coin", "USDT") if method.get("auto_verify") in ("binance", "binance_pay") else "BDT",
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
        quoted_rate: float | None = None,
        admin_note: str = "",
        verification_id: str | None = None,
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
                quote = await self._quote(method, amount, values)
                if quoted_rate is not None and abs(quote["rate"] - quoted_rate) > 1e-9:
                    raise InvalidInputError("The payment rate changed. Please start the deposit again.")
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
                    amount,
                    clean_tx,
                    quote["rate"],
                    quote["pay_amount"],
                    admin_note or "",
                    quote["paid_currency"],
                )
                if verification_id is not None:
                    await conn.execute(
                        "INSERT INTO payment_verification_attempts(deposit_id,provider,verify_id,status) VALUES($1,'zinipay',$2,'reserved')",
                        deposit_id, verification_id,
                    )
        except asyncpg.UniqueViolationError as exc:
            if exc.constraint_name == "deposit_one_pending":
                raise PendingDepositError("You already have a deposit waiting for review.") from exc
            raise DuplicateTransactionError("This transaction ID has already been submitted.") from exc

        self.notifier.in_background(self._notify_new_request(deposit_id, tg_user_id, user["username"], quote, clean_tx, admin_note=admin_note))
        return deposit_id

    async def _notify_new_request(
        self,
        deposit_id: int,
        tg_user_id: int,
        username: str | None,
        quote: dict[str, Any],
        transaction_id: str,
        admin_note: str = "",
    ) -> None:
        symbol = escape(await self.settings.get("currency_symbol"))
        customer = f"@{escape(username)}" if username else "No username"
        payable = f"\n{ICON_COIN} <b>Customer pays:</b> {quote['pay_amount']:.2f} (rate {quote['rate']:g})" if quote["rate"] != 1 else ""
        note_line = f"\n⚠️ <b>Note:</b> <i>{escape(admin_note)}</i>" if admin_note else ""

        # Reviewing a deposit is the most time-critical thing an operator does:
        # a customer has already sent money and is waiting. Offer the decision
        # here rather than only a link that costs a browser and a login.
        console = get_settings().console_url
        rows = [[
            InlineKeyboardButton(
                text="Approve",
                callback_data=f"adm_dep_ask_approve_{deposit_id}",
                style="success",
                icon_custom_emoji_id=Icons.CONFIRM,
            ),
            InlineKeyboardButton(
                text="Reject",
                callback_data=f"adm_dep_ask_reject_{deposit_id}",
                style="danger",
                icon_custom_emoji_id=Icons.CROSS,
            ),
        ]]
        if console:
            rows.append([
                InlineKeyboardButton(
                    text="Open in Console",
                    url=f"{console}/#deposits",
                    icon_custom_emoji_id=Icons.DEPOSIT,
                )
            ])
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

        await self.notifier.send_admin(
            f"{ICON_DEPOSIT} <b>New Deposit Request #{deposit_id}</b>\n\n"
            f"{ICON_ACCOUNT} <b>Customer:</b> {customer}\n"
            f"{ICON_ID} <b>Customer ID:</b> <code>{tg_user_id}</code>\n"
            f"{ICON_DEPOSIT} <b>Method:</b> {escape(quote['method_name'])}\n"
            f"{ICON_MONEY} <b>Amount:</b> <code>{quote['amount']:.2f} {symbol}</code>{payable}\n"
            f"{ICON_KEY} <b>TrxID:</b> <code>{escape(transaction_id)}</code>"
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

    async def list(self, status: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
        where, params = "", []
        if status:
            params.append(status)
            where = " AND d.status = $1"
        async with self.db.connect() as conn:
            total = await conn.fetchval(f"SELECT COUNT(*) FROM deposits d WHERE 1=1{where}", *params)
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
        method_name = escape(deposit["method_name"])
        if notify_customer:
            self.notifier.in_background(
                self._notify_customer(
                    deposit["tg_user_id"],
                    lambda symbol: (
                        f"{ICON_CHECK} <b>Deposit Approved!</b>\n\n"
                        f"{ICON_MONEY} <b>Amount:</b> <code>{amount:.2f} {symbol}</code>\n"
                        f"{ICON_DEPOSIT} <b>Method:</b> {method_name}\n"
                        f"{ICON_BALANCE} <b>Balance:</b> <code>{details['new_balance']:.2f} {symbol}</code>"
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
                InlineKeyboardButton(text="Contact Support", url=f"https://t.me/{clean_sup}", icon_custom_emoji_id=Icons.SUPPORT)
            ]])
        else:
            support_kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="Contact Support", callback_data="open_support", icon_custom_emoji_id=Icons.SUPPORT)
            ]])

        self.notifier.in_background(
            self._notify_customer(
                tg_user_id,
                lambda symbol: (
                    f"{ICON_WARNING} <b>Deposit Rejected</b>\n\n"
                    f"{ICON_ACCOUNT} <b>Customer:</b> {u_handle}\n"
                    f"{ICON_ID} <b>Customer ID:</b> <code>{tg_user_id}</code>\n"
                    f"{ICON_DEPOSIT} <b>Method:</b> {method_name}\n"
                    f"{ICON_MONEY} <b>Amount:</b> <code>{amount:.2f} {symbol}</code>\n"
                    f"{ICON_KEY} <b>TrxID:</b> <code>{trx_id}</code>\n"
                    f"{ICON_NOTE} <b>Reason:</b> {escape(admin_note)}"
                ),
                keyboard=support_kb,
            )
        )
        return True, "Deposit rejected.", {"tg_user_id": deposit["tg_user_id"], "amount": deposit["amount"], "reason": admin_note}

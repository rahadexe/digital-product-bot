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

from app.core.money import money
from app.db import Database, affected
from app.services.audit import record
from app.services.errors import InvalidInputError
from app.services.notifications import Notifier
from app.services.settings import SettingsService

TRANSACTION_ID = re.compile(r"[A-Za-z0-9_\-]{6,80}")
CUSTOMER_DEPOSIT_COLUMNS = (
    "id, method_name, amount, pay_amount, rate_to_currency, transaction_id, status, admin_note, created_at, reviewed_at"
)
METHOD_FIELDS = (
    "name",
    "account_info",
    "instructions",
    "min_deposit",
    "rate_to_currency",
    "is_active",
    "sort_order",
    "auto_verify",
    "auto_verify_network",
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
    ) -> int:
        async with self.db.transaction() as conn:
            method_id = await conn.fetchval(
                """
                INSERT INTO deposit_methods (name, account_info, instructions, min_deposit, rate_to_currency,
                                             sort_order, is_active, auto_verify, auto_verify_network)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id
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
            row = await conn.fetchrow(
                "SELECT * FROM deposit_methods WHERE auto_verify = 'binance_pay' OR auto_verify = 'binance' OR lower(name) LIKE '%binance%' ORDER BY id LIMIT 1 FOR UPDATE"
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
                                                 sort_order, is_active, auto_verify, auto_verify_network)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id
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
    async def _quote(self, method: Any, amount: float) -> dict[str, Any]:
        symbol = await self.settings.get("currency_symbol")
        limit = await self.settings.number("max_deposit_limit")
        if amount < method["min_deposit"]:
            raise InvalidInputError(f"The minimum deposit for this method is {symbol}{method['min_deposit']:.2f}.")
        if amount > limit:
            raise InvalidInputError(f"The maximum single deposit is {symbol}{limit:.2f}. Contact support for larger payments.")
        rate = float(method["rate_to_currency"])
        return {
            "method_id": method["id"],
            "method_name": method["name"],
            "account_info": method["account_info"],
            "instructions": method["instructions"] or "",
            "amount": amount,
            "rate": rate,
            "pay_amount": round(amount * rate, 4),
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
        self, tg_user_id: int, method_id: int, amount: float, transaction_id: str, *, quoted_rate: float | None = None
    ) -> int:
        paused = await self.settings.paused_message()
        if paused:
            raise InvalidInputError(paused)
        amount = money(amount, positive=True)
        clean_tx = str(transaction_id).strip()
        if not TRANSACTION_ID.fullmatch(clean_tx):
            raise InvalidInputError("Invalid transaction ID.")
        try:
            async with self.db.transaction() as conn:
                user = await conn.fetchrow("SELECT id, username, is_banned FROM users WHERE tg_user_id = $1", tg_user_id)
                if not user or user["is_banned"]:
                    raise InvalidInputError("Account unavailable or suspended.")
                method = await conn.fetchrow("SELECT * FROM deposit_methods WHERE id = $1 AND is_active = 1", method_id)
                if not method:
                    raise InvalidInputError("Payment method is no longer available.")
                quote = await self._quote(method, amount)
                if quoted_rate is not None and abs(quote["rate"] - quoted_rate) > 1e-9:
                    raise InvalidInputError("The payment rate changed. Please start the deposit again.")
                deposit_id = await conn.fetchval(
                    """
                    INSERT INTO deposits (user_id, tg_user_id, method_id, method_name, amount, transaction_id,
                                          status, rate_to_currency, pay_amount)
                    VALUES ($1, $2, $3, $4, $5, $6, 'pending', $7, $8) RETURNING id
                    """,
                    user["id"],
                    tg_user_id,
                    method_id,
                    method["name"],
                    amount,
                    clean_tx,
                    quote["rate"],
                    quote["pay_amount"],
                )
        except asyncpg.UniqueViolationError as exc:
            if exc.constraint_name == "deposit_one_pending":
                raise PendingDepositError("You already have a deposit waiting for review.") from exc
            raise DuplicateTransactionError("This transaction ID has already been submitted.") from exc

        self.notifier.in_background(self._notify_new_request(deposit_id, tg_user_id, user["username"], quote, clean_tx))
        return deposit_id

    async def _notify_new_request(
        self, deposit_id: int, tg_user_id: int, username: str | None, quote: dict[str, Any], transaction_id: str
    ) -> None:
        symbol = escape(await self.settings.get("currency_symbol"))
        customer = f"@{escape(username)}" if username else "No username"
        payable = f"\n💱 <b>Customer pays:</b> {quote['pay_amount']:.2f} (rate {quote['rate']:g})" if quote["rate"] != 1 else ""
        await self.notifier.send_admin(
            f"🔔 <b>New Deposit Request #{deposit_id}</b>\n\n"
            f"👤 <b>User:</b> {customer} (<code>{tg_user_id}</code>)\n"
            f"💳 <b>Method:</b> {escape(quote['method_name'])}\n"
            f"💵 <b>Wallet credit:</b> {symbol}{quote['amount']:.2f}{payable}\n"
            f"🔖 <b>Transaction ID:</b> <code>{escape(transaction_id)}</code>\n\n"
            "<i>Verify the payment, then review it in the Admin Console.</i>",
            event="deposit",
        )

    async def _notify_customer(self, tg_user_id: int, text_for_symbol: Callable[[str], str]) -> None:
        symbol = escape(await self.settings.get("currency_symbol"))
        await self.notifier.send(tg_user_id, text_for_symbol(symbol))

    async def pending_for(self, tg_user_id: int) -> dict[str, Any] | None:
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                f"SELECT {CUSTOMER_DEPOSIT_COLUMNS} FROM deposits WHERE tg_user_id = $1 AND status = 'pending' "
                "ORDER BY id DESC LIMIT 1",
                tg_user_id,
            )
            return dict(row) if row else None

    async def history(self, tg_user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        """A customer's own deposits, newest first, with what they were asked to pay and the review outcome."""
        async with self.db.connect() as conn:
            rows = await conn.fetch(
                f"SELECT {CUSTOMER_DEPOSIT_COLUMNS} FROM deposits WHERE tg_user_id = $1 ORDER BY id DESC LIMIT $2",
                tg_user_id,
                limit,
            )
        return [dict(row) for row in rows]

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

    async def approve(self, deposit_id: int, admin_note: str = "") -> tuple[bool, str, dict[str, Any] | None]:
        async with self.db.transaction() as conn:
            deposit = await conn.fetchrow("SELECT * FROM deposits WHERE id = $1 FOR UPDATE", deposit_id)
            if not deposit:
                return False, "Deposit record not found.", None
            if deposit["status"] != "pending":
                return False, f"Deposit already marked as {deposit['status']}.", None
            if await conn.fetchval(
                "SELECT 1 FROM deposits WHERE id <> $1 AND status = 'approved' "
                "AND lower(btrim(transaction_id)) = lower(btrim($2))",
                deposit_id,
                deposit["transaction_id"],
            ):
                return False, "This transaction has already been credited.", None
            amount = money(deposit["amount"], positive=True)
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
        self.notifier.in_background(
            self._notify_customer(
                deposit["tg_user_id"],
                lambda symbol: (
                    f"🎉 <b>Deposit Approved!</b>\n\n"
                    f"Your deposit of <b>{symbol}{amount:.2f}</b> ({method_name}) has been approved.\n"
                    f"💰 <b>Updated Balance:</b> <code>{symbol}{details['new_balance']:.2f}</code>\n\n"
                    "<i>You can now browse the Shop and place orders.</i>"
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
            await conn.execute(
                "UPDATE deposits SET status = 'rejected', admin_note = $1, reviewed_at = now() WHERE id = $2",
                admin_note,
                deposit_id,
            )
            await record(
                conn, "reject_deposit", f"Rejected Deposit #{deposit_id} for user {deposit['tg_user_id']}. Reason: {admin_note}"
            )

        amount = deposit["amount"]
        self.notifier.in_background(
            self._notify_customer(
                deposit["tg_user_id"],
                lambda symbol: (
                    f"⚠️ <b>Deposit Rejected</b>\n\n"
                    f"Your deposit request of <b>{symbol}{amount:.2f}</b> could not be approved.\n"
                    f"📝 <b>Reason:</b> {escape(admin_note)}\n\n"
                    "<i>If you believe this was an error, please contact Customer Support with payment proof.</i>"
                ),
            )
        )
        return True, "Deposit rejected.", {"tg_user_id": deposit["tg_user_id"], "amount": deposit["amount"], "reason": admin_note}

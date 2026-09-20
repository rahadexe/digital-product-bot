"""ZiniPay In-Bot Transaction Verification Service.

Implements the official 2-step Transaction Verification API:
1. POST https://api.zinipay.com/v1/trx/verify (checks amount & TrxID against merchant statement, returns masked data and id)
2. POST https://api.zinipay.com/v1/trx/confirm (consumes transaction permanently so it cannot be double-spent)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.db import Database
from app.services.audit import record
from app.services.deposits import DepositService, DuplicateTransactionError
from app.services.errors import InvalidInputError
from app.services.notifications import Notifier
from app.services.settings import SettingsService
from app.services.http import gateway_http

logger = logging.getLogger(__name__)

ZINIPAY_TRX_API = "https://api.zinipay.com/v1/trx"


class ZiniPayVerificationService:
    """Service to automatically verify bKash, Nagad, and Rocket TrxIDs via ZiniPay."""

    def __init__(
        self,
        db: Database,
        settings: SettingsService,
        deposits: DepositService,
        notifier: Notifier,
        config: Settings,
        timeout: float = 15.0,
    ):
        self.db = db
        self.settings = settings
        self.deposits = deposits
        self.notifier = notifier
        self.config = config
        self.timeout = timeout
        self.http = gateway_http(timeout)

    async def get_api_key(self) -> str:
        """Fetch ZiniPay API key from DB settings, falling back to config / env."""
        db_key = (await self.settings.get("zinipay_api_key") or "").strip()
        if db_key:
            return db_key
        return (self.config.zinipay_api_key or "").strip()

    async def is_enabled(self) -> bool:
        """Check if ZiniPay verification API is enabled with an API key."""
        key = await self.get_api_key()
        return bool(key) and await self.settings.flag("zinipay_enabled")

    async def verify(self, amount: float, transaction_id: str) -> dict[str, Any]:
        """Step 1: Validate transaction existence, amount, and status."""
        api_key = await self.get_api_key()
        if not api_key:
            return {"ok": False, "reason": "no_key", "message": "ZiniPay API key is not configured."}

        clean_tx = str(transaction_id).strip()
        url = f"{ZINIPAY_TRX_API}/verify"
        headers = {
            "zini-api-key": api_key,
            "zinipay-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "transactionId": clean_tx,
            "amount": amount,
        }

        try:
            res = await self.http.post(url, json=payload, headers=headers)
            status = res.status_code
            try:
                data = res.json()
            except Exception:
                data = {}
        except Exception as exc:
            logger.warning("ZiniPay verify connection error: %s", exc)
            return {"ok": False, "reason": "connection_error", "message": f"Connection error: {exc}"}

        # Handle successful verification
        is_success = bool(data.get("success") is True or data.get("status") is True or (status == 200 and data.get("data") and not data.get("error") and not data.get("code")))
        if status == 200 and is_success:
            trx_data = data.get("data") or {}
            return {
                "ok": True,
                "id": trx_data.get("id"),
                "trx_id": trx_data.get("trxID") or trx_data.get("transactionId") or clean_tx,
                "amount": float(trx_data.get("amount") or amount),
                "provider": trx_data.get("provider") or trx_data.get("method") or "bKash/Nagad",
                "sender": trx_data.get("sender") or trx_data.get("senderNumber") or trx_data.get("masked_sender") or "",
                "status": trx_data.get("status"),
                "raw": trx_data,
            }

        # Parse specific errors
        msg = str(data.get("message") or "")
        code = str(data.get("code") or "")

        if "amount must be equal" in msg.lower() or "amount mismatch" in msg.lower():
            return {"ok": False, "reason": "amount_mismatch", "message": msg}
        elif "already used" in msg.lower():
            return {"ok": False, "reason": "already_used", "message": msg}
        elif "not enabled" in msg.lower():
            return {"ok": False, "reason": "not_enabled", "message": msg}
        elif code in ("INSUFFICIENT_CREDITS", "CREDITS_EXPIRED"):
            return {"ok": False, "reason": "credits_error", "message": msg or code}
        elif status == 404 or "not found" in msg.lower():
            return {"ok": False, "reason": "not_found", "message": msg or "Transaction not found."}

        return {"ok": False, "reason": "error", "message": msg or f"HTTP {status}"}

    async def confirm(self, amount: float, transaction_id: str, verify_id: int) -> dict[str, Any]:
        """Step 2: Permanently consume the transaction so it cannot be reused."""
        api_key = await self.get_api_key()
        if not api_key:
            return {"ok": False, "message": "ZiniPay API key missing."}

        clean_tx = str(transaction_id).strip()
        url = f"{ZINIPAY_TRX_API}/confirm"
        headers = {
            "zini-api-key": api_key,
            "zinipay-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "transactionId": clean_tx,
            "amount": amount,
            "id": verify_id,
        }

        try:
            res = await self.http.post(url, json=payload, headers=headers)
            status = res.status_code
            try:
                data = res.json()
            except Exception:
                data = {}
        except Exception as exc:
            logger.warning("ZiniPay confirm connection error: %s", exc)
            return {"ok": False, "message": f"Connection error: {exc}"}

        is_success = bool(data.get("success") is True or data.get("status") is True or (status == 200 and data.get("data") and not data.get("error") and not data.get("code")))
        if status == 200 and is_success:
            confirm_data = data.get("data") or {}
            return {
                "ok": True,
                "provider": confirm_data.get("provider") or confirm_data.get("method") or "bKash/Nagad",
                "sender_number": confirm_data.get("senderNumber") or confirm_data.get("sender") or "",
                "amount": float(confirm_data.get("amount") or amount),
                "transaction_id": confirm_data.get("transactionId") or clean_tx,
                "raw": confirm_data,
            }

        msg = str(data.get("message") or f"Confirm failed (HTTP {status})")
        return {"ok": False, "message": msg}

    async def claim(
        self,
        tg_user_id: int,
        method_id: int,
        amount: float,
        transaction_id: str,
        *,
        quoted_rate: float = 1.0,
    ) -> dict[str, Any]:
        """Attempt to auto-verify transaction via ZiniPay, or fall back to manual deposit queue."""
        clean_tx = str(transaction_id).strip()

        # 1. Pre-check: has this TrxID already been credited?
        existing = await self.deposits.find_by_transaction(clean_tx)
        if existing:
            if existing.get("status") == "approved":
                raise DuplicateTransactionError("This Transaction ID has already been credited.")
            if existing.get("tg_user_id") == tg_user_id and existing.get("status") == "pending":
                raise InvalidInputError("You already submitted this Transaction ID. It is awaiting review.")

        # 2. Check if ZiniPay API key is configured
        has_key = await self.is_enabled()
        if not has_key:
            # Fallback: create regular pending deposit request for manual admin review
            dep_id = await self.deposits.create_request(
                tg_user_id, method_id, amount, clean_tx, quoted_rate=quoted_rate, admin_note="ZiniPay API key is not configured"
            )
            return {
                "auto_verified": False,
                "fallback_manual": True,
                "deposit_id": dep_id,
                "detail": "Request submitted for admin review.",
            }

        # 3. Step 1: Verify via ZiniPay
        verify_res = await self.verify(amount, clean_tx)
        logger.info("ZiniPay verification outcome: ok=%s", verify_res.get("ok"))
        if not verify_res.get("ok") and verify_res.get("reason") == "not_found":
            logger.info("Trx %s not found on first attempt. Waiting 3s for SMS sync retry...", clean_tx)
            await asyncio.sleep(3.0)
            verify_res = await self.verify(amount, clean_tx)
            logger.info("ZiniPay verification retry: ok=%s", verify_res.get("ok"))
        if not verify_res.get("ok"):
            reason = verify_res.get("reason")
            msg = verify_res.get("message") or ""

            if reason == "amount_mismatch":
                return {
                    "auto_verified": False,
                    "error": "amount_mismatch",
                    "detail": "The amount you entered does not match the payment receipt SMS. Please check the amount and try again.",
                }
            elif reason == "already_used":
                return {
                    "auto_verified": False,
                    "error": "already_used",
                    "detail": "This transaction ID has already been consumed or used in ZiniPay.",
                }
            elif reason == "not_found":
                return {
                    "auto_verified": False,
                    "error": "not_found",
                    "detail": "Transaction not found on ZiniPay yet. Please ensure the TrxID and amount match your SMS receipt, or wait 1 minute for SMS sync and try again.",
                }
            else:
                # System error / not enabled / insufficient credits -> graceful fallback to manual review
                note = f"ZiniPay: {msg}" if msg else "Verification unavailable"
                dep_id = await self.deposits.create_request(
                    tg_user_id, method_id, amount, clean_tx, quoted_rate=quoted_rate, admin_note=note
                )
                return {
                    "auto_verified": False,
                    "fallback_manual": True,
                    "deposit_id": dep_id,
                    "detail": f"Verification unavailable ({msg}). Submitted for admin review.",
                }

        # Reserve locally before the irreversible external confirmation. Every crash
        # after this point leaves a reviewable deposit and a durable attempt.
        verify_id = verify_res.get("id")
        if verify_id is None:
            raise InvalidInputError("The gateway returned an incomplete verification. Please try again.")
        dep_id = await self.deposits.create_request(
            tg_user_id, method_id, amount, clean_tx, quoted_rate=quoted_rate,
            verification_id=str(verify_id), admin_note="Automatic verification in progress.",
        )
        async with self.db.transaction() as conn:
            await conn.execute(
                "UPDATE payment_verification_attempts SET status='confirming',updated_at=now() WHERE deposit_id=$1", dep_id
            )
        confirm_res = await self.confirm(amount, clean_tx, verify_id)
        provider = confirm_res.get("provider") or verify_res.get("provider") or "bKash/Nagad"
        sender = confirm_res.get("sender_number") or verify_res.get("sender") or ""
        note = f"Auto-verified via ZiniPay ({provider})"
        if not confirm_res.get("ok"):
            note = "Gateway confirmation uncertain; verify the merchant statement before approval. " + str(confirm_res.get("message") or "")[:200]
        async with self.db.transaction() as conn:
            await conn.execute(
                "UPDATE payment_verification_attempts SET status=$2,note=$3,updated_at=now() WHERE deposit_id=$1",
                dep_id, "confirmed" if confirm_res.get("ok") else "review", note,
            )
            await conn.execute("UPDATE deposits SET admin_note=$2 WHERE id=$1 AND status='pending'", dep_id, note)
        if not confirm_res.get("ok"):
            return {"auto_verified": False, "fallback_manual": True, "deposit_id": dep_id,
                    "detail": "Your payment is saved for review. Please do not pay again."}

        approved, app_msg, _ = await self.deposits.approve(dep_id, admin_note=note, notify_customer=False)
        async with self.db.transaction() as conn:
            persisted = await conn.fetchval("SELECT status FROM deposits WHERE id=$1", dep_id)
            if persisted == "approved":
                await conn.execute("UPDATE payment_verification_attempts SET status='completed',updated_at=now() WHERE deposit_id=$1", dep_id)
        if persisted != "approved":
            return {"auto_verified": False, "fallback_manual": True, "deposit_id": dep_id,
                    "detail": "Payment confirmation is saved. " + app_msg}
        return {"auto_verified": True, "credited": True, "deposit_id": dep_id, "amount": amount,
                "provider": provider, "sender": sender, "transaction_id": clean_tx,
                "detail": "Payment confirmed and wallet credited."}

    async def recover(self) -> None:
        """Confirmed outcomes can be replayed; ambiguous provider calls need review."""
        async with self.db.transaction() as conn:
            stale = await conn.fetch(
                "UPDATE payment_verification_attempts SET status='review',updated_at=now(), "
                "note='Interrupted gateway confirmation. Check the merchant statement; do not ask the customer to pay again.' "
                "WHERE status IN ('reserved','confirming') AND updated_at < now()-interval '2 minutes' RETURNING deposit_id,note"
            )
            for row in stale:
                await conn.execute("UPDATE deposits SET admin_note=$2 WHERE id=$1 AND status='pending'", row['deposit_id'], row['note'])
            confirmed = await conn.fetch(
                "SELECT deposit_id,note FROM payment_verification_attempts WHERE status='confirmed' ORDER BY updated_at LIMIT 20"
            )
        for row in confirmed:
            await self.deposits.approve(row['deposit_id'], row['note'])
            async with self.db.connect() as conn:
                await conn.execute(
                    "UPDATE payment_verification_attempts SET status=CASE WHEN d.status='approved' THEN 'completed' ELSE 'review' END, "
                    "updated_at=now() FROM deposits d WHERE d.id=deposit_id AND deposit_id=$1 AND d.status<>'pending'", row['deposit_id']
                )

"""ZiniPay In-Bot Transaction Verification Service.

Implements the official 2-step Transaction Verification API:
1. POST https://api.zinipay.com/v1/trx/verify (checks amount & TrxID against merchant statement, returns masked data and id)
2. POST https://api.zinipay.com/v1/trx/confirm (consumes transaction permanently so it cannot be double-spent)
"""

from __future__ import annotations

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

    async def get_api_key(self) -> str:
        """Fetch ZiniPay API key from DB settings, falling back to config / env."""
        db_key = (await self.settings.get("zinipay_api_key") or "").strip()
        if db_key:
            return db_key
        return (self.config.zinipay_api_key or "").strip()

    async def is_enabled(self) -> bool:
        """Check if ZiniPay verification API is enabled with an API key."""
        key = await self.get_api_key()
        return bool(key)

    async def verify(self, amount: float, transaction_id: str) -> dict[str, Any]:
        """Step 1: Validate transaction existence, amount, and status."""
        api_key = await self.get_api_key()
        if not api_key:
            return {"ok": False, "reason": "no_key", "message": "ZiniPay API key is not configured."}

        clean_tx = str(transaction_id).strip()
        url = f"{ZINIPAY_TRX_API}/verify"
        headers = {
            "zinipay-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "transactionId": clean_tx,
            "amount": amount,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(url, json=payload, headers=headers)
                status = res.status_code
                try:
                    data = res.json()
                except Exception:
                    data = {}
        except Exception as exc:
            logger.warning("ZiniPay verify connection error: %s", exc)
            return {"ok": False, "reason": "connection_error", "message": f"Connection error: {exc}"}

        # Handle successful verification
        if status == 200 and data.get("success"):
            trx_data = data.get("data") or {}
            return {
                "ok": True,
                "id": trx_data.get("id"),
                "trx_id": trx_data.get("trxID") or clean_tx,
                "amount": trx_data.get("amount") or amount,
                "provider": trx_data.get("provider") or "Unknown",
                "sender": trx_data.get("sender") or "",
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
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(url, json=payload, headers=headers)
                status = res.status_code
                try:
                    data = res.json()
                except Exception:
                    data = {}
        except Exception as exc:
            logger.warning("ZiniPay confirm connection error: %s", exc)
            return {"ok": False, "message": f"Connection error: {exc}"}

        if status == 200 and data.get("success"):
            confirm_data = data.get("data") or {}
            return {
                "ok": True,
                "provider": confirm_data.get("provider"),
                "sender_number": confirm_data.get("senderNumber"),
                "amount": confirm_data.get("amount") or amount,
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
                tg_user_id, method_id, amount, clean_tx, quoted_rate=quoted_rate
            )
            return {
                "auto_verified": False,
                "fallback_manual": True,
                "deposit_id": dep_id,
                "detail": "Request submitted for admin review.",
            }

        # 3. Step 1: Verify via ZiniPay
        verify_res = await self.verify(amount, clean_tx)
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
                dep_id = await self.deposits.create_request(
                    tg_user_id, method_id, amount, clean_tx, quoted_rate=quoted_rate
                )
                return {
                    "auto_verified": False,
                    "fallback_manual": True,
                    "deposit_id": dep_id,
                    "detail": f"Verification unavailable ({msg}). Submitted for admin review.",
                }

        # 4. Step 2: Confirm via ZiniPay
        verify_id = verify_res.get("id")
        confirm_res = await self.confirm(amount, clean_tx, verify_id)
        if not confirm_res.get("ok"):
            # Fallback to manual review if confirmation failed
            dep_id = await self.deposits.create_request(
                tg_user_id, method_id, amount, clean_tx, quoted_rate=quoted_rate
            )
            return {
                "auto_verified": False,
                "fallback_manual": True,
                "deposit_id": dep_id,
                "detail": f"Verification confirmed with note: {confirm_res.get('message')}. Submitted for admin review.",
            }

        # 5. Success! Create and instantly approve the deposit
        provider = confirm_res.get("provider") or verify_res.get("provider") or "bKash/Nagad"
        sender = confirm_res.get("sender_number") or verify_res.get("sender") or ""
        dep_id = await self.deposits.create_request(
            tg_user_id, method_id, amount, clean_tx, quoted_rate=quoted_rate
        )

        note = f"Auto-verified via ZiniPay ({provider})"
        if sender:
            note += f", Sender: {sender}"

        # Approve and credit user wallet immediately (notify_customer=False so the bot handler sends the rich receipt)
        approved, app_msg, _ = await self.deposits.approve(dep_id, admin_note=note, notify_customer=False)
        if not approved:
            logger.error("Failed to approve auto-verified ZiniPay deposit #%s: %s", dep_id, app_msg)

        async with self.db.transaction() as conn:
            await record(
                conn,
                "zinipay_deposit_auto_verified",
                f"Deposit #{dep_id}: {amount:.2f} BDT auto-verified via {provider} ({clean_tx})",
            )

        return {
            "auto_verified": True,
            "credited": True,
            "deposit_id": dep_id,
            "amount": amount,
            "provider": provider,
            "sender": sender,
            "transaction_id": clean_tx,
            "detail": f"Confirmed and credited instantly via {provider}.",
        }

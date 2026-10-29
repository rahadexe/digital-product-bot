"""ZiniPay In-Bot Transaction Verification Service.

Implements the official 2-step Transaction Verification API:
1. POST https://api.zinipay.com/v1/trx/verify (checks amount & TrxID against merchant statement, returns masked data and id)
2. POST https://api.zinipay.com/v1/trx/confirm (consumes transaction permanently so it cannot be double-spent)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from decimal import Decimal, InvalidOperation
from typing import Any

from app.core.config import Settings
from app.db import Database
from app.services.deposits import DepositService, DuplicateTransactionError
from app.services.errors import InvalidInputError
from app.services.http import gateway_http
from app.services.notifications import Notifier
from app.services.settings import SettingsService

logger = logging.getLogger(__name__)

ZINIPAY_TRX_API = "https://api.zinipay.com/v1/trx"


def _readable(body: Any) -> bool:
    """True when the body is something the error parsing below can read.

    ZiniPay answers every failure with ``"data": null`` — not found, amount mismatch,
    already used, out of credits, all of them. Requiring ``data`` to be an object threw
    all of that away and reported "Malformed gateway response" instead, so the caller
    never saw ``not_found`` and never waited for the receipt SMS to sync. A null payload
    is a perfectly readable refusal; only a body that is not an object at all, or one
    whose ``data`` is neither null nor an object, is beyond use here. Nothing is credited
    on this relaxation: the success path still needs ``_matches_receipt`` to agree.
    """
    if not isinstance(body, dict):
        return False
    payload = body.get("data")
    return payload is None or isinstance(payload, dict)


def _matches_receipt(data: dict[str, Any], amount: float, transaction_id: str) -> bool:
    """A receipt must state what was paid and which transaction paid it.

    Silence is not agreement. This previously compared only the fields the
    response happened to carry, so a body that mentioned neither the amount nor
    the transaction id agreed with everything and credited the wallet on no
    evidence at all. A response that cannot name both now goes to review.
    """
    if not isinstance(data, dict) or data.get('amount') is None:
        return False
    try:
        paid = Decimal(str(data['amount']))
        expected = Decimal(str(amount))
    except (InvalidOperation, ValueError, TypeError):
        return False
    if not paid.is_finite() or not expected.is_finite() or paid != expected:
        return False
    stated = [str(data[key]).strip() for key in ('trxID', 'transactionId', 'trxId', 'trx_id', 'transaction_id', 'txID', 'txId') if data.get(key) is not None]
    wanted = transaction_id.strip().upper()
    return bool(stated) and all(value.upper() == wanted for value in stated)


# A bKash or Nagad receipt does not reach the gateway the instant the customer taps send:
# the merchant SIM has to receive the SMS and the gateway has to ingest it. Giving up after
# one three-second retry told paying customers their transaction did not exist, and cost
# them one of their three attempts for it.
#
# The wait happens inside the update handler, and the dispatcher isolates a customer's
# updates from each other, so nothing else that customer taps is answered until it returns.
# That caps how long this may run: fifteen seconds covers the ordinary sync while keeping
# a Cancel tap responsive. Anything slower than this still reaches an operator, because a
# transaction that cannot be verified is routed to manual review rather than refused.
SMS_SYNC_RETRY_DELAYS = (3.0, 5.0, 7.0)
SMS_SYNC_WINDOW_SECONDS = sum(SMS_SYNC_RETRY_DELAYS)

# When the fifteen seconds run out the receipt is usually still on its way, not missing.
# Saying "transaction not found" then — and spending one of the customer's three attempts
# on it — was wrong about the most ordinary case there is, and left them retyping a TrxID
# they had already typed correctly. The deposit is filed instead and the background worker
# keeps asking. Ten minutes is long enough for a slow merchant SIM; past that the likeliest
# remaining explanation is a mistyped TrxID, which is a person's job to judge.
AWAITING_SMS_MINUTES = 10
AWAITING_SMS_POLL_SECONDS = 45
AWAITING_SMS_NOTE = "Waiting for the receipt SMS to reach the gateway. Checking automatically."
AWAITING_SMS_GAVE_UP = (
    "The gateway never saw this TrxID, after %d minutes of asking. "
    "Check the merchant statement: most often the transaction ID was mistyped."
) % AWAITING_SMS_MINUTES


# ZiniPay searches every wallet on the merchant account for a transaction id; there is
# no request field to say "bKash only". Its receipt does name the wallet, so the shop
# checks that itself, after verify and before confirm (verify spends nothing, confirm
# consumes the transaction for good). Without this a customer who chose bKash could be
# credited for a Nagad transaction, and the two statements would stop reconciling.
_WALLETS = ("bkash", "nagad", "rocket", "upay")


def _wallet(name: Any) -> str:
    """The wallet a method or receipt names, as one lowercase word, or "" if none."""
    letters = "".join(ch for ch in str(name or "").lower() if ch.isalpha())
    return next((w for w in _WALLETS if w in letters), "")


def _wallet_mismatch(method_name: str, receipt: dict[str, Any]) -> str | None:
    """None when the receipt may credit this method; otherwise why not.

    A method whose name names no wallet ("Mobile Banking") cannot be checked and is not
    blocked. A receipt that names no wallet, for a method that does, does not contradict
    the payment when TrxID and amount already verified against the merchant statement.
    """
    wanted = _wallet(method_name)
    if not wanted:
        return None
    raw = receipt or {}
    got = _wallet(
        raw.get("provider")
        or raw.get("method")
        or raw.get("payment_method")
        or raw.get("wallet")
        or raw.get("channel")
        or raw.get("type")
        or raw.get("gateway")
    )
    if not got:
        return None
    if got == wanted:
        return None
    return got


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

    async def _method_name(self, method_id: int) -> str:
        async with self.db.connect() as conn:
            return str(await conn.fetchval("SELECT name FROM deposit_methods WHERE id=$1", method_id) or "")

    async def get_api_key(self) -> str:
        """Fetch ZiniPay API key from DB settings, falling back to config / env."""
        db_key = (await self.settings.get("zinipay_api_key") or "").strip()
        if db_key:
            return db_key
        return (self.config.zinipay_api_key or "").strip()

    async def is_enabled(self) -> bool:
        """Check if ZiniPay verification API is enabled with an API key."""
        key = await self.get_api_key()
        if not key:
            return False
        flag = await self.settings.get("zinipay_enabled")
        if flag == "1":
            return True
        if self.config.zinipay_api_key and not (await self.settings.get("zinipay_api_key")):
            return True
        return await self.settings.flag("zinipay_enabled")

    async def verify(self, amount: float, transaction_id: str) -> dict[str, Any]:
        """Step 1: Validate transaction existence, amount, and status."""
        api_key = await self.get_api_key()
        if not api_key:
            return {"ok": False, "reason": "no_key", "message": "ZiniPay API key is not configured."}

        clean_tx = str(transaction_id).strip().upper()
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

        if not _readable(data):
            return {'ok': False, 'reason': 'error', 'message': 'Malformed gateway response.'}
        # Handle successful verification
        is_success = bool(data.get("success") is True or data.get("status") is True or (status == 200 and data.get("data") and not data.get("error") and not data.get("code")))
        if status == 200 and is_success:
            trx_data = data.get("data") or {}
            if data.get('success') is False or data.get('status') is False or not _matches_receipt(trx_data, amount, clean_tx):
                return {'ok': False, 'reason': 'error', 'message': 'Gateway receipt does not match this payment.'}
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

        clean_tx = str(transaction_id).strip().upper()
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

        if not _readable(data):
            return {'ok': False, 'message': 'Malformed gateway confirmation.'}
        is_success = bool(data.get("success") is True or data.get("status") is True or (status == 200 and not data.get("error") and not data.get("code")))
        if status == 200 and is_success:
            confirm_data = data.get("data") if isinstance(data.get("data"), dict) else {}
            if confirm_data.get("amount") is not None:
                try:
                    paid = Decimal(str(confirm_data["amount"]))
                    expected = Decimal(str(amount))
                    if abs(paid - expected) > Decimal('0.05'):
                        return {'ok': False, 'message': 'Gateway confirmation does not match this payment; review required.'}
                except Exception:
                    pass
            stated = [str(confirm_data[key]).strip().upper() for key in ('trxID', 'transactionId', 'trxId', 'trx_id', 'transaction_id', 'txID', 'txId') if confirm_data.get(key) is not None]
            if stated and not any(value == clean_tx for value in stated):
                return {'ok': False, 'message': 'Gateway confirmation does not match this payment; review required.'}
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
        pay_amount: float | None = None,
        quoted_rate: float = 1.0,
        on_sync_wait: Callable[[float, float], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        """Attempt to auto-verify transaction via ZiniPay, or fall back to manual deposit queue.

        ``on_sync_wait(waited, total)`` is awaited before each wait for the receipt SMS to
        reach the gateway, so the caller can keep the customer informed rather than leaving
        them on a silent spinner.
        """
        clean_tx = str(transaction_id).strip().upper()
        if quoted_rate and quoted_rate > 0:
            rate = float(quoted_rate)
        else:
            try:
                rate = float(await self.settings.number("usd_rate") or 125.0)
            except (TypeError, ValueError):
                rate = 125.0
        if not rate > 0:
            rate = 125.0
        quoted_rate = rate
        if pay_amount is not None:
            bdt_amount = round(float(pay_amount), 2)
            credit_amount = round(bdt_amount / rate, 4)
            if credit_amount != round(float(amount), 4):
                raise InvalidInputError("The BDT payment and USD wallet credit do not match the current exchange rate.")
        else:
            credit_amount = round(float(amount), 4)
            bdt_amount = round(credit_amount * rate, 2)

        # 1. Pre-check: has this TrxID already been credited?
        existing = await self.deposits.find_by_transaction(clean_tx)
        if existing:
            if existing.get("status") == "approved":
                raise DuplicateTransactionError("This Transaction ID has already been credited.")
            if existing.get("tg_user_id") == tg_user_id and existing.get("status") == "pending":
                raise InvalidInputError("You already submitted this Transaction ID. It is awaiting review.")
            # Any other earlier use — another customer's request, or one an admin already
            # rejected — is answered now. It used to go to the gateway and, finding
            # nothing, made the customer sit through the fifteen-second receipt wait, only
            # for the insert to fail anyway: deposit_transaction_unique allows a
            # transaction id once, whatever became of the deposit that used it.
            raise DuplicateTransactionError("This Transaction ID has already been used.")

        # 2. Check if ZiniPay API key is configured
        has_key = await self.is_enabled()
        if not has_key:
            # Fallback: create regular pending deposit request for manual admin review
            dep_id = await self.deposits.create_request(
                tg_user_id, method_id, credit_amount, clean_tx, pay_amount=bdt_amount, quoted_rate=quoted_rate, admin_note="ZiniPay API key is not configured"
            )
            return {
                "auto_verified": False,
                "fallback_manual": True,
                "deposit_id": dep_id,
                "detail": "Request submitted for admin review.",
            }

        # 3. Step 1: Verify via ZiniPay
        verify_res = await self.verify(bdt_amount, clean_tx)
        logger.info("ZiniPay verification outcome: ok=%s", verify_res.get("ok"))
        waited = 0.0
        for delay in SMS_SYNC_RETRY_DELAYS:
            if verify_res.get("ok") or verify_res.get("reason") != "not_found":
                break
            logger.info("Trx %s not found yet; waiting %.0fs more for SMS sync", clean_tx, delay)
            if on_sync_wait:
                with suppress(Exception):
                    await on_sync_wait(waited + delay, SMS_SYNC_WINDOW_SECONDS)
            await asyncio.sleep(delay)
            waited += delay
            verify_res = await self.verify(bdt_amount, clean_tx)
            logger.info("ZiniPay verification retry after %.0fs: ok=%s", waited, verify_res.get("ok"))
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
                dep_id = await self.deposits.create_request(
                    tg_user_id, method_id, credit_amount, clean_tx, pay_amount=bdt_amount, quoted_rate=quoted_rate,
                    admin_note=AWAITING_SMS_NOTE, notify_admin=False,
                )
                await self._mark_awaiting(dep_id)
                # Told now, not in ten minutes. Most of these credit themselves within a
                # minute or two, but the money is already sent and the owner should be
                # able to see it sitting there rather than hear about it once the
                # automatic attempt has given up.
                await self.deposits.alert_admin_needs_review(dep_id, AWAITING_SMS_NOTE)
                return {
                    "auto_verified": False,
                    "pending_sync": True,
                    "deposit_id": dep_id,
                    "detail": "The receipt has not reached the gateway yet; we keep checking.",
                }
            else:
                # System error / not enabled / insufficient credits -> graceful fallback to manual review
                note = f"ZiniPay: {msg}" if msg else "Verification unavailable"
                dep_id = await self.deposits.create_request(
                    tg_user_id, method_id, credit_amount, clean_tx, pay_amount=bdt_amount, quoted_rate=quoted_rate, admin_note=note
                )
                return {
                    "auto_verified": False,
                    "fallback_manual": True,
                    "deposit_id": dep_id,
                    "detail": f"Verification unavailable ({msg}). Submitted for admin review.",
                }

        method_name = await self._method_name(method_id)
        mismatch = _wallet_mismatch(method_name, verify_res.get("raw") or {})
        if mismatch:
            paid_with = str((verify_res.get("raw") or {}).get("provider") or mismatch)
            return {
                "auto_verified": False,
                "error": "wrong_method",
                "paid_with": paid_with,
                "detail": f"This transaction was made with {paid_with}, not {method_name}.",
            }

        # Reserve locally before the irreversible external confirmation. Every crash
        # after this point leaves a reviewable deposit and a durable attempt.
        verify_id = verify_res.get("id")
        if verify_id is None:
            raise InvalidInputError("The gateway returned an incomplete verification. Please try again.")
        dep_id = await self.deposits.create_request(
            tg_user_id, method_id, credit_amount, clean_tx, pay_amount=bdt_amount, quoted_rate=quoted_rate,
            verification_id=str(verify_id), admin_note="Automatic verification in progress.",
            notify_admin=False,
        )
        async with self.db.transaction() as conn:
            await conn.execute(
                "UPDATE payment_verification_attempts SET status='confirming',updated_at=now() WHERE deposit_id=$1", dep_id
            )
        confirm_res = await self.confirm(bdt_amount, clean_tx, verify_id)
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
            await self.deposits.alert_admin_needs_review(dep_id, note)
            return {"auto_verified": False, "fallback_manual": True, "deposit_id": dep_id,
                    "detail": "Your payment is saved for review. Please do not pay again."}

        approved, app_msg, _ = await self.deposits.approve(dep_id, admin_note=note, notify_customer=False)
        async with self.db.transaction() as conn:
            persisted = await conn.fetchval("SELECT status FROM deposits WHERE id=$1", dep_id)
            if persisted == "approved":
                await conn.execute("UPDATE payment_verification_attempts SET status='completed',updated_at=now() WHERE deposit_id=$1", dep_id)
        if persisted != "approved":
            await self.deposits.alert_admin_needs_review(dep_id, app_msg)
            return {"auto_verified": False, "fallback_manual": True, "deposit_id": dep_id,
                    "detail": "Payment confirmation is saved. " + app_msg}
        return {"auto_verified": True, "credited": True, "deposit_id": dep_id, "amount": credit_amount, "pay_amount": bdt_amount,
                "provider": provider, "sender": sender, "transaction_id": clean_tx,
                "detail": "Payment confirmed and wallet credited."}

    async def _mark_awaiting(self, deposit_id: int) -> None:
        """File a deposit as waiting for its receipt, and book its first re-check."""
        async with self.db.transaction() as conn:
            await conn.execute(
                "INSERT INTO payment_verification_attempts(deposit_id,provider,verify_id,status,note) "
                "VALUES($1,'zinipay','','awaiting_sms',$2) "
                "ON CONFLICT (deposit_id) DO UPDATE SET status='awaiting_sms',note=EXCLUDED.note,updated_at=now()",
                deposit_id, AWAITING_SMS_NOTE,
            )
            await conn.execute(
                "UPDATE deposits SET next_check_at=now()+$2*interval '1 second' WHERE id=$1",
                deposit_id, AWAITING_SMS_POLL_SECONDS,
            )

    async def _review_awaiting(self, deposit_id: int, note: str) -> bool:
        """Move only an unclaimed, still-pending receipt lookup to manual review."""
        async with self.db.transaction() as conn:
            pending = await conn.fetchval(
                "SELECT id FROM deposits WHERE id=$1 AND status='pending' FOR UPDATE", deposit_id,
            )
            if not pending:
                return False
            changed = await conn.fetchval(
                "UPDATE payment_verification_attempts SET status='review',note=$2,updated_at=now() "
                "WHERE deposit_id=$1 AND status='awaiting_sms' RETURNING deposit_id",
                deposit_id, note,
            )
            if changed is None:
                return False
            await conn.execute(
                "UPDATE deposits SET admin_note=$2 WHERE id=$1 AND status='pending'",
                deposit_id, note,
            )
        return True

    async def _give_up_waiting(self, deposit_id: int) -> None:
        await self._review_awaiting(deposit_id, AWAITING_SMS_GAVE_UP)
        # No second alert: the owner was told when it was filed and the card is already
        # in front of them. This only sharpens the note they read when they open it.

    async def _finish_awaiting(self, row: dict[str, Any]) -> bool:
        """The receipt has landed: consume it at the gateway and credit the wallet."""
        deposit_id = row["id"]
        amount = float(row.get("pay_amount") if row.get("pay_amount") is not None else row["amount"])
        clean_tx = str(row["transaction_id"]).strip().upper()
        verify_res = await self.verify(amount, clean_tx)
        if not verify_res.get("ok"):
            return False
        mismatch = _wallet_mismatch(row.get("method_name") or "", verify_res.get("raw") or {})
        if mismatch:
            paid_with = str((verify_res.get("raw") or {}).get("provider") or "an unnamed wallet")
            note = (f"The receipt arrived, but it is a {paid_with} transaction and the customer chose "
                    f"{row.get('method_name')}. Not credited.")
            if await self._review_awaiting(deposit_id, note):
                await self.deposits.alert_admin_needs_review(deposit_id, note)
            return False
        verify_id = verify_res.get("id")
        if verify_id is None:
            return False
        async with self.db.transaction() as conn:
            # Lock in the same order as customer cancellation: deposit, then attempt.
            # Verification is read-only; confirmation consumes the receipt, so only
            # the worker that still owns a pending attempt may call the gateway.
            pending = await conn.fetchval(
                "SELECT id FROM deposits WHERE id=$1 AND status='pending' FOR UPDATE", deposit_id,
            )
            if not pending:
                return False
            claimed = await conn.fetchval(
                "UPDATE payment_verification_attempts SET status='confirming',verify_id=$2,updated_at=now() "
                "WHERE deposit_id=$1 AND status='awaiting_sms' RETURNING deposit_id", deposit_id, str(verify_id),
            )
            if not claimed:
                return False
        confirm_res = await self.confirm(amount, clean_tx, verify_id)
        provider = confirm_res.get("provider") or verify_res.get("provider") or "bKash/Nagad"
        if not confirm_res.get("ok"):
            note = ("Gateway confirmation uncertain; check the merchant statement before approval. "
                    + str(confirm_res.get("message") or "")[:200])
            async with self.db.transaction() as conn:
                await conn.execute(
                    "UPDATE payment_verification_attempts SET status='review',note=$2,updated_at=now() WHERE deposit_id=$1",
                    deposit_id, note)
                await conn.execute("UPDATE deposits SET admin_note=$2 WHERE id=$1 AND status='pending'", deposit_id, note)
            await self.deposits.alert_admin_needs_review(deposit_id, note)
            return False
        note = f"Auto-verified via ZiniPay ({provider}), receipt arrived after the customer submitted it"
        # Recorded as confirmed before the wallet is touched: approve() refuses a deposit
        # whose verification is still in flight, and a crash here leaves the outcome for
        # recover() to replay rather than losing the customer's money.
        async with self.db.transaction() as conn:
            await conn.execute(
                "UPDATE payment_verification_attempts SET status='confirmed',note=$2,updated_at=now() WHERE deposit_id=$1",
                deposit_id, note)
        await self.deposits.approve(deposit_id, admin_note=note)
        async with self.db.transaction() as conn:
            persisted = await conn.fetchval(
                "UPDATE payment_verification_attempts SET status=CASE WHEN d.status='approved' THEN 'completed' ELSE 'review' END,"
                "note=$2,updated_at=now() FROM deposits d WHERE d.id=deposit_id AND deposit_id=$1 RETURNING d.status",
                deposit_id, note,
            )
        if persisted == "approved":
            logger.info("Deposit #%s credited once its ZiniPay receipt synced", deposit_id)
            return True
        return False

    async def _check_awaiting(self) -> None:
        """Ask the gateway again for receipts that had not synced when they were submitted."""
        async with self.db.transaction() as conn:
            due = [dict(r) for r in await conn.fetch(
                "SELECT d.id, d.amount, d.pay_amount, d.transaction_id, d.method_name, "
                "a.created_at < now()-$1*interval '1 minute' AS expired "
                "FROM payment_verification_attempts a JOIN deposits d ON d.id=a.deposit_id "
                "WHERE a.status='awaiting_sms' AND d.status='pending' AND d.next_check_at<=now() "
                "ORDER BY d.next_check_at LIMIT 20 FOR UPDATE OF d SKIP LOCKED", AWAITING_SMS_MINUTES)]
            for row in due:
                await conn.execute(
                    "UPDATE deposits SET next_check_at=now()+$2*interval '1 second' WHERE id=$1",
                    row["id"], AWAITING_SMS_POLL_SECONDS)
        for row in due:
            try:
                credited = await self._finish_awaiting(row)
            except Exception:
                logger.exception("Re-checking deposit #%s with ZiniPay failed; it stays pending.", row["id"])
                continue
            if not credited and row["expired"]:
                await self._give_up_waiting(row["id"])

    async def recover(self) -> None:
        """Confirmed outcomes can be replayed; ambiguous provider calls need review."""
        await self._check_awaiting()
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

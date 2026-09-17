"""Automatic deposits through ZiniPay.

Each top-up is an invoice stored before the customer is sent to ZiniPay. ZiniPay's callback carries no
signature, so it only prompts a check: an invoice is credited only after ZiniPay's verify API reports it
COMPLETED for this invoice, this reference and this amount. Crediting inserts an approved deposit and moves
the invoice to completed in one transaction, so repeated callbacks and checks can never credit twice.
"""

from __future__ import annotations

import logging
import secrets
from decimal import ROUND_HALF_UP, Decimal
from html import escape
from typing import Any
from urllib.parse import urlsplit

import asyncpg
import httpx

from app.core.config import Settings
from app.core.money import money
from app.db import Database
from app.services.audit import record
from app.services.errors import InvalidInputError
from app.services.notifications import Notifier
from app.services.settings import SettingsService

logger = logging.getLogger("app.services.payments")

PROVIDER = "zinipay"
ZINIPAY_API = "https://api.zinipay.com/v1/payment"
LOCAL_CURRENCY = "BDT"
# A customer who taps Pay again for the same amount gets the invoice they already opened.
REUSE_PENDING_SECONDS = 30 * 60
MAX_INVOICES_PER_HOUR = 10
# Unpaid invoices stop being checked after this long.
EXPIRE_AFTER_HOURS = 24
AMOUNT_TOLERANCE = Decimal("0.01")
REFERENCE_PREFIX = "SM"


class PaymentProviderError(Exception):
    """ZiniPay could not be reached or refused the request. Nothing is credited."""


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _provider_message(status: int, body: dict[str, Any], missing: str = "") -> str:
    message = str(body.get("message") or "").strip()[:160]
    if status in (200, 201):
        # Accepted, but unusable: name the piece that was absent and what did arrive.
        fields = ", ".join(sorted(body)[:8]) or "nothing"
        return f"ZiniPay replied {status} without {missing or 'what a payment needs'}. It sent: {fields}."
    return f"ZiniPay HTTP {status}: {message}" if message else f"ZiniPay HTTP {status}"


def _nested(body: dict[str, Any]) -> list[dict[str, Any]]:
    """ZiniPay wraps its answer differently between environments; look one level down as well."""
    inner = [value for key, value in body.items() if key in ("data", "result", "payment", "invoice") and isinstance(value, dict)]
    return [body, *inner]


def _field(body: dict[str, Any], *names: str) -> str:
    for source in _nested(body):
        for name in names:
            value = source.get(name)
            if isinstance(value, (str, int, float)) and str(value).strip():
                return str(value).strip()
    return ""


def _is_zinipay_url(url: str) -> bool:
    """A customer may only be sent to ZiniPay itself, whichever domain it serves the page from."""
    parts = urlsplit(url)
    labels = (parts.hostname or "").lower().split(".")
    return parts.scheme == "https" and len(labels) >= 2 and labels[-2] == "zinipay"


class ZiniPayClient:
    """The two calls the integration needs. The API key is sent in a header and never logged."""

    def __init__(self, api_key: str, timeout: float = 20.0):
        self.api_key = api_key
        self.timeout = timeout

    async def _post(self, path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{ZINIPAY_API}/{path}",
                    json=payload,
                    headers={"zini-api-key": self.api_key, "Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            raise PaymentProviderError(f"ZiniPay could not be reached ({type(exc).__name__}).") from None
        try:
            body = response.json()
        except ValueError:
            body = {}
        return response.status_code, body if isinstance(body, dict) else {}

    async def create_invoice(self, payload: dict[str, Any]) -> dict[str, Any]:
        """The invoice's id and the page to send the customer to; anything else is not a usable answer."""
        status, body = await self._post("create", payload)
        # Live ZiniPay names the invoice only by the val_id it was given; the sandbox also sends invoice_id.
        invoice_id = _field(body, "invoice_id", "invoiceId", "id") or _field(body, "val_id", "valId")
        payment_url = _field(body, "payment_url", "paymentUrl", "checkout_url", "url")
        if status not in (200, 201) or not payment_url:
            raise PaymentProviderError(_provider_message(status, body, "a payment link"))
        if not invoice_id and payment_url:
            parts = [p for p in urlsplit(payment_url).path.split("/") if p]
            if parts:
                invoice_id = parts[-1]
        if not invoice_id:
            raise PaymentProviderError(_provider_message(status, body, "an invoice id"))
        return {"invoice_id": invoice_id, "payment_url": payment_url}

    async def verify(self, invoice_id: str, reference: str = "") -> dict[str, Any] | None:
        """ZiniPay's view of an invoice, or None when it does not know the invoice (unknown or expired)."""
        payload = {"invoice_id": invoice_id}
        if reference:
            # ZiniPay accepts either name for an invoice; sending both saves a guess about which it kept.
            payload["val_id"] = reference
        status, body = await self._post("verify", payload)
        if status == 404:
            return None
        # Flattened, so a wrapped answer is read the same way as a plain one.
        answer: dict[str, Any] = {}
        for source in reversed(_nested(body)):
            answer.update({key: value for key, value in source.items() if not isinstance(value, dict)})
        if status != 200 or "status" not in answer:
            raise PaymentProviderError(_provider_message(status, body))
        return answer


def _public(row: Any) -> dict[str, Any]:
    """What the customer may see about their own payment."""
    status = row["status"]
    return {
        "reference": row["reference"],
        "status": status,
        "credit_amount": float(row["credit_amount"]),
        "pay_amount": float(row["pay_amount"]),
        "rate": float(row["rate"]),
        "local_currency": LOCAL_CURRENCY,
        "payment_url": row["payment_url"] if status == "pending" else None,
        "created_at": row["created_at"].isoformat(),
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
    }


class PaymentService:
    def __init__(self, db: Database, settings: SettingsService, notifier: Notifier, config: Settings):
        self.db = db
        self.settings = settings
        self.notifier = notifier
        self.config = config

    # --- configuration ---
    def client(self, api_key: str) -> ZiniPayClient:
        return ZiniPayClient(api_key)

    async def _api_key(self) -> str:
        return (await self.settings.get("zinipay_api_key")).strip() or self.config.zinipay_api_key.strip()

    def public_base_url(self, brand_url: str = "") -> str:
        """The store's public HTTPS origin, taken from zinipay_brand_url or WEBAPP_URL; ZiniPay requires it for redirects."""
        raw = brand_url.strip() or self.config.webapp_url.strip()
        if not raw:
            return ""
        if "://" not in raw:
            raw = f"https://{raw}"
        parts = urlsplit(raw)
        if parts.netloc:
            return f"https://{parts.netloc}"
        return ""

    async def instant_options(self) -> dict[str, Any] | None:
        """Instant payment as the storefront offers it, or None when it is off or not fully configured."""
        values = await self.settings.values()
        base = self.public_base_url(values.get("zinipay_brand_url", ""))
        if values["zinipay_enabled"] != "1" or not await self._api_key() or not base:
            return None
        return {
            "label": values["zinipay_label"],
            "rate": float(values["zinipay_rate"]),
            "min_amount": float(values["zinipay_min_deposit"]),
            "local_currency": LOCAL_CURRENCY,
        }

    async def status(self) -> dict[str, Any]:
        values = await self.settings.values()
        base = self.public_base_url(values.get("zinipay_brand_url", ""))
        has_key = bool(await self._api_key())
        async with self.db.connect() as conn:
            counts = {
                row["status"]: row["count"]
                for row in await conn.fetch("SELECT status, count(*) FROM payment_invoices GROUP BY status")
            }
            # Why the last attempt failed, so the reason is on the settings page instead of only in the logs.
            failure = await conn.fetchrow(
                "SELECT last_error, updated_at FROM payment_invoices WHERE last_error IS NOT NULL "
                "ORDER BY updated_at DESC LIMIT 1"
            )
        return {
            "enabled": values["zinipay_enabled"] == "1",
            "has_api_key": has_key,
            "public_url": base,
            "webhook_url": f"{base}/api/payments/zinipay/webhook" if base else "",
            "ready": values["zinipay_enabled"] == "1" and has_key and bool(base),
            "counts": counts,
            "last_error": failure["last_error"] if failure else "",
            "last_error_at": failure["updated_at"].isoformat() if failure else None,
        }

    async def test_connection(self) -> dict[str, Any]:
        key = await self._api_key()
        if not key:
            return {"ok": False, "message": "Add the ZiniPay API key first."}
        try:
            # An unknown invoice is reported as not found only once the key has been accepted.
            await self.client(key).verify(f"connection-check-{secrets.token_hex(6)}")
        except PaymentProviderError as exc:
            return {"ok": False, "message": str(exc)}
        return {"ok": True, "message": "ZiniPay accepted the API key."}

    async def test_invoice(self) -> dict[str, Any]:
        """Ask ZiniPay for a payment page the way a customer would, and report exactly what it answers."""
        options = await self.instant_options()
        if not options:
            return {"ok": False, "message": "Switch instant payments on, save the API key, and set WEBAPP_URL or Brand URL first."}
        values = await self.settings.values()
        base = self.public_base_url(values.get("zinipay_brand_url", ""))
        rate = _decimal(values["zinipay_rate"])
        pay_amount = (_decimal(options["min_amount"]) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        reference = f"{REFERENCE_PREFIX}{secrets.token_hex(8).upper()}"
        return_url = f"{base}/app/?payment={reference}"
        payload = {
            "cus_name": "Test",
            "cus_email": f"test@{urlsplit(base).hostname}",
            "amount": float(pay_amount),
            "val_id": reference,
            "metadata": {"reference": reference, "test": True},
            "redirect_url": return_url,
            "return_type": "GET",
            "cancel_url": f"{return_url}&cancelled=1",
            "webhook_url": f"{base}/api/payments/zinipay/webhook",
        }
        # Nothing is stored: an unpaid ZiniPay invoice simply expires.
        try:
            body = await self.client(await self._api_key()).create_invoice(payload)
        except PaymentProviderError as exc:
            return {"ok": False, "message": str(exc)}
        return {
            "ok": True,
            "message": f"ZiniPay opened a payment page for {pay_amount} {LOCAL_CURRENCY}. Nothing was charged.",
            "payment_url": str(body.get("payment_url") or ""),
        }

    # --- invoices ---
    async def create_invoice(self, tg_user_id: int, amount: Any) -> dict[str, Any]:
        paused = await self.settings.paused_message()
        if paused:
            raise InvalidInputError(paused)
        options = await self.instant_options()
        if not options:
            raise InvalidInputError("Instant payment is not available right now.")
        try:
            credit = money(amount, positive=True)
        except (TypeError, ValueError):
            raise InvalidInputError("Enter a valid amount, for example 10 or 25.50.") from None
        values = await self.settings.values()
        symbol = values["currency_symbol"]
        if credit < options["min_amount"]:
            raise InvalidInputError(f"The minimum is {symbol}{options['min_amount']:.2f}.")
        limit = float(values["max_deposit_limit"])
        if credit > limit:
            raise InvalidInputError(f"The maximum single deposit is {symbol}{limit:.2f}.")
        rate = _decimal(values["zinipay_rate"])
        pay_amount = (_decimal(credit) * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        async with self.db.transaction() as conn:
            user = await conn.fetchrow("SELECT id, first_name, is_banned FROM users WHERE tg_user_id = $1 FOR UPDATE", tg_user_id)
            if not user or user["is_banned"]:
                raise InvalidInputError("Account unavailable or suspended.")
            reusable = await conn.fetchrow(
                "SELECT * FROM payment_invoices WHERE tg_user_id = $1 AND provider = $2 AND status = 'pending' "
                "AND credit_amount = $3 AND rate = $4 AND created_at > now() - $5 * interval '1 second' "
                "ORDER BY id DESC LIMIT 1",
                tg_user_id,
                PROVIDER,
                _decimal(credit),
                rate,
                REUSE_PENDING_SECONDS,
            )
            if reusable:
                return _public(reusable)
            recent = await conn.fetchval(
                "SELECT count(*) FROM payment_invoices WHERE tg_user_id = $1 AND created_at > now() - interval '1 hour'",
                tg_user_id,
            )
            if recent >= MAX_INVOICES_PER_HOUR:
                raise InvalidInputError("Too many payment attempts. Please wait a little and try again.")
            reference = f"{REFERENCE_PREFIX}{secrets.token_hex(8).upper()}"
            row = await conn.fetchrow(
                "INSERT INTO payment_invoices (reference, provider, user_id, tg_user_id, credit_amount, pay_amount, rate) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *",
                reference,
                PROVIDER,
                user["id"],
                tg_user_id,
                _decimal(credit),
                pay_amount,
                rate,
            )

        base = self.public_base_url(values.get("zinipay_brand_url", ""))
        return_url = f"{base}/app/?payment={reference}"
        payload = {
            "cus_name": (user["first_name"] or "Customer")[:60],
            "cus_email": f"tg{tg_user_id}@{urlsplit(base).hostname or 'store.local'}",
            "amount": float(pay_amount),
            "val_id": reference,
            "metadata": {"reference": reference, "tg_user_id": tg_user_id},
            "redirect_url": return_url,
            "return_type": "GET",
            "cancel_url": f"{return_url}&cancelled=1",
            "webhook_url": f"{base}/api/payments/zinipay/webhook",
        }
        try:
            body = await self.client(await self._api_key()).create_invoice(payload)
            payment_url = body["payment_url"]
            if not _is_zinipay_url(payment_url):
                raise PaymentProviderError(f"ZiniPay returned an unexpected payment address ({urlsplit(payment_url).hostname}).")
        except PaymentProviderError as exc:
            logger.warning("ZiniPay invoice %s could not be created: %s", reference, exc)
            async with self.db.transaction() as conn:
                await conn.execute(
                    "UPDATE payment_invoices SET status = 'failed', last_error = $1, updated_at = now() WHERE id = $2",
                    str(exc)[:300],
                    row["id"],
                )
            self.notifier.in_background(
                self.notifier.send_admin(
                    f"⚠️ <b>ZiniPay refused a payment</b>\n\n{escape(str(exc))}\n\n"
                    "<i>Check the API key in Settings → Payments, and that the brand website in ZiniPay "
                    "is this shop's domain.</i>"
                )
            )
            raise InvalidInputError("The payment page could not be opened. Please try again in a moment.") from None

        async with self.db.transaction() as conn:
            row = await conn.fetchrow(
                "UPDATE payment_invoices SET status = 'pending', provider_invoice_id = $1, payment_url = $2, updated_at = now() "
                "WHERE id = $3 RETURNING *",
                body["invoice_id"],
                payment_url,
                row["id"],
            )
            await record(
                conn,
                "payment_invoice_created",
                f"ZiniPay {reference} for user {tg_user_id}: {credit:.2f} credit, {pay_amount} {LOCAL_CURRENCY}",
            )
        return _public(row)

    async def refresh(self, reference: str, tg_user_id: int | None = None) -> dict[str, Any] | None:
        """Ask ZiniPay about a pending invoice and apply the answer. Owner-bound when ``tg_user_id`` is given."""
        async with self.db.connect() as conn:
            row = await conn.fetchrow("SELECT * FROM payment_invoices WHERE reference = $1", reference)
        if not row or (tg_user_id is not None and row["tg_user_id"] != tg_user_id):
            return None
        if row["status"] != "pending" or not row["provider_invoice_id"]:
            return _public(row)
        key = await self._api_key()
        if not key:
            return _public(row)
        try:
            result = await self.client(key).verify(row["provider_invoice_id"], row["reference"])
        except PaymentProviderError as exc:
            logger.warning("ZiniPay verify for %s failed: %s", reference, exc)
            return _public(row)
        return _public(await self._apply(row["id"], result))

    async def handle_webhook(self, invoice_id: str, reference: str) -> None:
        """A callback only names an invoice; ZiniPay is then asked directly before anything changes."""
        if not invoice_id and not reference:
            return
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                "SELECT reference FROM payment_invoices WHERE provider = $1 AND (provider_invoice_id = $2 OR reference = $3) LIMIT 1",
                PROVIDER,
                invoice_id,
                reference,
            )
        if row:
            await self.refresh(row["reference"])

    async def recheck_pending(self, limit: int = 20, idle_seconds: int = 45) -> int:
        """Ask ZiniPay about unpaid invoices nobody has checked recently, least recently checked first."""
        if not await self._api_key():
            return 0
        async with self.db.connect() as conn:
            rows = await conn.fetch(
                "SELECT reference FROM payment_invoices WHERE status = 'pending' "
                "AND updated_at < now() - $2 * interval '1 second' ORDER BY updated_at LIMIT $1",
                limit,
                idle_seconds,
            )
        for row in rows:
            await self.refresh(row["reference"])
        return len(rows)

    async def _fail(self, conn: asyncpg.Connection, row: Any, reason: str, *, alert: bool) -> Any:
        updated = await conn.fetchrow(
            "UPDATE payment_invoices SET status = 'failed', last_error = $1, updated_at = now() WHERE id = $2 RETURNING *",
            reason[:300],
            row["id"],
        )
        await record(conn, "payment_failed", f"ZiniPay {row['reference']} for user {row['tg_user_id']}: {reason}")
        if alert:
            self.notifier.in_background(
                self.notifier.send_admin(
                    f"⚠️ <b>Automatic payment needs a look</b>\n\nReference <code>{escape(row['reference'])}</code>, "
                    f"user <code>{row['tg_user_id']}</code>\n{escape(reason)}\n\n<i>Nothing was credited. Check it in ZiniPay.</i>"
                )
            )
        return updated

    async def _apply(self, invoice_id: int, result: dict[str, Any] | None) -> Any:
        credited: tuple[Any, Any, int] | None = None
        async with self.db.transaction() as conn:
            row = await conn.fetchrow("SELECT * FROM payment_invoices WHERE id = $1 FOR UPDATE", invoice_id)
            if row["status"] != "pending":
                return row
            raw_status = str(result.get("status") or "").strip().upper() if result is not None else ""
            status = "COMPLETED" if raw_status in ("COMPLETED", "TRUE", "1", "PAID", "SUCCESS") else raw_status
            if result is None or status == "PENDING":
                # Still unpaid (or unknown to ZiniPay): note the check, and stop checking once it is too old.
                return await conn.fetchrow(
                    "UPDATE payment_invoices SET status = CASE WHEN created_at < now() - $2 * interval '1 hour' "
                    "THEN 'expired' ELSE status END, updated_at = now() WHERE id = $1 RETURNING *",
                    invoice_id,
                    EXPIRE_AFTER_HOURS,
                )
            if status == "FAILED":
                return await self._fail(conn, row, "ZiniPay reported the payment as failed.", alert=False)
            if status != "COMPLETED":
                return row

            # The answer must belong to this invoice and cover exactly what the customer was asked to pay.
            problems = []
            answered_invoice = str(result.get("invoice_id") or result.get("invoiceId") or "")
            answered_reference = str(result.get("val_id") or result.get("valId") or "")
            if answered_invoice and answered_invoice != row["provider_invoice_id"]:
                problems.append("the verified invoice does not match")
            if answered_reference and answered_reference != row["reference"]:
                problems.append("the reference does not match")
            if not answered_invoice and not answered_reference:
                problems.append("the answer names no invoice")
            paid = _decimal(result.get("without_fee", result.get("amount")))
            expected = _decimal(row["pay_amount"])
            if abs(paid - expected) > AMOUNT_TOLERANCE:
                problems.append(f"paid {paid:.2f} {LOCAL_CURRENCY} but the invoice was for {expected:.2f} {LOCAL_CURRENCY}")
            if problems:
                reason = "; ".join(problems)
                return await self._fail(conn, row, f"{reason[0].upper()}{reason[1:]}.", alert=True)

            transaction_id = str(result.get("transaction_id") or "").strip()
            if not transaction_id or transaction_id.upper() == "N/A":
                transaction_id = row["provider_invoice_id"]
            method = str(result.get("payment_method") or result.get("provider") or "").strip()[:30]
            method_name = f"ZiniPay ({method})" if method else "ZiniPay"
            try:
                async with conn.transaction():
                    deposit_id = await conn.fetchval(
                        """
                        INSERT INTO deposits (user_id, tg_user_id, method_id, method_name, amount, transaction_id,
                                              status, admin_note, rate_to_currency, pay_amount, reviewed_at)
                        VALUES ($1, $2, NULL, $3, $4, $5, 'approved', $6, $7, $8, now()) RETURNING id
                        """,
                        row["user_id"],
                        row["tg_user_id"],
                        method_name,
                        row["credit_amount"],
                        transaction_id[:80],
                        f"Paid automatically via ZiniPay ({row['reference']})",
                        row["rate"],
                        row["pay_amount"],
                    )
            except asyncpg.UniqueViolationError:
                return await self._fail(
                    conn, row, f"Transaction ID {transaction_id} was already recorded for another deposit.", alert=True
                )
            balance = await conn.fetchval(
                "UPDATE users SET balance = balance + $1, updated_at = now() WHERE tg_user_id = $2 RETURNING balance",
                row["credit_amount"],
                row["tg_user_id"],
            )
            row = await conn.fetchrow(
                "UPDATE payment_invoices SET status = 'completed', provider_transaction_id = $1, payment_method = $2, "
                "deposit_id = $3, last_error = NULL, completed_at = now(), updated_at = now() WHERE id = $4 RETURNING *",
                transaction_id,
                method or None,
                deposit_id,
                invoice_id,
            )
            await record(
                conn,
                "payment_completed",
                f"ZiniPay {row['reference']}: credited {float(row['credit_amount']):.2f} to user {row['tg_user_id']} "
                f"(deposit #{deposit_id}, {row['pay_amount']} {LOCAL_CURRENCY}, TrxID {transaction_id})",
            )
            credited = (row, balance, deposit_id)

        if credited:
            self.notifier.in_background(self._notify_completed(*credited))
        return row

    async def _notify_completed(self, row: Any, balance: Any, deposit_id: int) -> None:
        symbol = escape(await self.settings.get("currency_symbol"))
        credit = float(row["credit_amount"])
        await self.notifier.send(
            row["tg_user_id"],
            f"✅ <b>Payment received</b>\n\n<b>{symbol}{credit:.2f}</b> has been added to your wallet.\n"
            f"💰 <b>Balance:</b> <code>{symbol}{float(balance or 0):.2f}</code>",
        )
        await self.notifier.send_admin(
            f"💳 <b>Automatic deposit #{deposit_id}</b>\n\n"
            f"👤 User <code>{row['tg_user_id']}</code>\n"
            f"💵 Credit {symbol}{credit:.2f} · paid {float(row['pay_amount']):.2f} {LOCAL_CURRENCY}\n"
            f"💳 {escape(row['payment_method'] or 'ZiniPay')} · TrxID <code>{escape(row['provider_transaction_id'] or '')}</code>"
        )

    async def list(self, status: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        where, params = "", []
        if status:
            params.append(status)
            where = " WHERE p.status = $1"
        async with self.db.connect() as conn:
            total = await conn.fetchval(f"SELECT count(*) FROM payment_invoices p{where}", *params)
            rows = await conn.fetch(
                f"""
                SELECT p.id, p.reference, p.provider, p.tg_user_id, u.username, u.first_name, p.credit_amount, p.pay_amount,
                       p.rate, p.status, p.provider_invoice_id, p.provider_transaction_id, p.payment_method, p.deposit_id,
                       p.last_error, p.created_at, p.completed_at
                FROM payment_invoices p LEFT JOIN users u ON u.tg_user_id = p.tg_user_id{where}
                ORDER BY p.id DESC LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
                """,
                *params,
                limit,
                offset,
            )
        return [dict(row) for row in rows], total

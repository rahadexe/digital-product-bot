"""Payment gateway callbacks. They are public, so they only prompt a server-side check with the gateway."""

from __future__ import annotations

import secrets
from html import escape
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.api.deps import ServicesDep
from app.services.sms_parser import parse_mfs_sms

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.get('/return', response_class=HTMLResponse)
async def payment_return(reference: str, services: ServicesDep):
    # The high-entropy reference exposes only the payment status, never wallet or identity data.
    if len(reference) > 80:
        return HTMLResponse('Invalid payment reference.', status_code=400)
    async with services.db.connect() as conn:
        status = await conn.fetchval('SELECT status FROM payment_invoices WHERE reference=$1', reference)
    messages = {
        'completed': ('Payment received', 'Your wallet has been credited. Return to the bot to continue.'),
        'failed': ('Payment needs review', 'Return to the bot and contact support with your receipt. Please do not pay again.'),
        'expired': ('Payment page expired', 'If you paid, contact support with your receipt before trying again.'),
    }
    title, message = messages.get(status, ('Checking your payment', 'Your payment is being checked. You can return to the bot; confirmed payments are credited automatically.'))
    if status is None:
        title, message = 'Payment reference unavailable', 'Return to the bot. If this was a test checkout, no wallet credit was requested.'
    username = await services.notifier.bot_username()
    refresh = '<meta http-equiv="refresh" content="5">' if status in ('created', 'pending') else ''
    return HTMLResponse(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        + refresh + '<title>' + escape(title) + '</title><style>body{font:18px system-ui;margin:10vh auto;padding:24px;max-width:480px;line-height:1.6}a{display:inline-block;padding:12px 20px;background:#165dce;color:white;border-radius:8px;text-decoration:none}</style>'
        + '<main><h1>' + escape(title) + '</h1><p>' + escape(message) + '</p><a href="https://t.me/'
        + escape(username, quote=True) + '">Return to bot</a></main></html>'
    )


@router.api_route("/zinipay/webhook", methods=["GET", "POST"])
async def zinipay_webhook(request: Request, services: ServicesDep):
    # ZiniPay sends the invoice in a JSON body or in the query string, without a signature. The invoice is
    # verified with ZiniPay's API before anything is credited, so a forged call cannot add money.
    data: dict[str, str] = {key: value for key, value in request.query_params.items()}
    body = None
    if request.method == "POST":
        try:
            body = await request.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            # 1. Statement sync event from ZiniPay (SMS automation webhook)
            event = str(body.get("event") or "")
            if event == "billing.payment_received" or ("transactionId" in body and "amount" in body):
                trx_id = str(body.get("transactionId") or body.get("transaction_id") or "").strip()
                try:
                    amt = float(body.get("amount") or 0.0)
                except (ValueError, TypeError):
                    amt = 0.0
                provider = str(body.get("provider") or "bKash")
                sender = str(body.get("senderNumber") or body.get("sender") or "")
                raw_msg = str(body.get("message") or "")
                if trx_id and amt > 0:
                    await services.deposits.record_received_transaction(
                        transaction_id=trx_id,
                        amount=amt,
                        provider=provider,
                        sender_number=sender,
                        raw_message=raw_msg,
                    )
                    return {"ok": True, "event": event, "transaction_id": trx_id, "amount": amt}

            data.update({key: str(value) for key, value in body.items() if isinstance(value, (str, int))})
    invoice_id = str(data.get("invoice_id") or data.get("invoiceId") or "")[:120]
    reference = str(data.get("val_id") or "")[:120]
    await services.payments.handle_webhook(invoice_id, reference)
    return {"received": True}


@router.api_route("/sms-webhook", methods=["GET", "POST"])
async def sms_statement_webhook(request: Request, services: ServicesDep):
    """Inbound webhook for Android SMS Forwarder apps and statement sync."""
    configured_secret = (await services.settings.get("sms_webhook_secret") or "").strip()
    if configured_secret:
        header_secret = request.headers.get("x-webhook-secret") or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        query_secret = request.query_params.get("secret")
        provided_secret = header_secret or query_secret
        if not provided_secret or not secrets.compare_digest(provided_secret, configured_secret):
            return JSONResponse({"ok": False, "error": "Unauthorized"}, status_code=401)

    raw_body: dict[str, Any] = {}
    if request.method == "POST":
        try:
            raw_body = await request.json()
        except Exception:
            raw_body = {}

    msg = str(raw_body.get("message") or raw_body.get("text") or raw_body.get("body") or request.query_params.get("message") or "").strip()
    sender = str(raw_body.get("from") or raw_body.get("sender") or request.query_params.get("from") or "").strip()
    trx_id = str(raw_body.get("transaction_id") or raw_body.get("transactionId") or raw_body.get("trx_id") or "").strip()
    amount_val = raw_body.get("amount")
    provider = str(raw_body.get("provider") or "").strip()

    # If raw SMS text is provided, parse it with Bangladeshi MFS parser
    if msg and (not trx_id or not amount_val):
        parsed = parse_mfs_sms(msg, sender_hint=sender)
        if parsed:
            trx_id = parsed["transaction_id"]
            amount_val = parsed["amount"]
            provider = provider or parsed["provider"]
            sender = parsed["sender_number"] or sender

    if not trx_id:
        return JSONResponse({"ok": False, "error": "No transaction ID found in payload or SMS text"}, status_code=400)

    try:
        amount = float(amount_val or 0.0)
    except (ValueError, TypeError):
        amount = 0.0

    if amount <= 0:
        return JSONResponse({"ok": False, "error": "Invalid or missing amount"}, status_code=400)

    provider = provider or "bKash"
    row = await services.deposits.record_received_transaction(
        transaction_id=trx_id,
        amount=amount,
        provider=provider,
        sender_number=sender,
        raw_message=msg,
    )

    return {
        "ok": True,
        "transaction_id": trx_id,
        "amount": amount,
        "provider": provider,
        "recorded": bool(row),
    }

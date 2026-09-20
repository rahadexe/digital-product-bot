"""Payment gateway callbacks. They are public, so they only prompt a server-side check with the gateway."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from html import escape

from app.api.deps import ServicesDep

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
    if request.method == "POST":
        try:
            body = await request.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            data.update({key: str(value) for key, value in body.items() if isinstance(value, (str, int))})
    invoice_id = str(data.get("invoice_id") or data.get("invoiceId") or "")[:120]
    reference = str(data.get("val_id") or "")[:120]
    await services.payments.handle_webhook(invoice_id, reference)
    return {"received": True}

"""Payment gateway callbacks. They are public, so they only prompt a server-side check with the gateway."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import ServicesDep

router = APIRouter(prefix="/api/payments", tags=["payments"])


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

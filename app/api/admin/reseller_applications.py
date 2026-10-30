from __future__ import annotations

from typing import Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from fastapi import APIRouter, HTTPException, Query

from app.api.admin.auth import WRITE
from app.api.admin.schemas import ResellerApplicationReviewPayload
from app.api.deps import ServicesDep

router = APIRouter()


@router.get("/reseller-applications")
async def list_reseller_applications(
    services: ServicesDep,
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    applications = await services.reseller_applications.list_applications(status=status, limit=limit, offset=offset)
    total = await services.reseller_applications.count_applications(status=status)
    summary = await services.reseller_applications.get_summary()
    return {"applications": applications, "total": total, "summary": summary}


@router.post("/reseller-applications/{app_id}/approve", dependencies=WRITE)
async def approve_reseller_application(
    app_id: int,
    payload: ResellerApplicationReviewPayload,
    services: ServicesDep,
):
    app = await services.reseller_applications.approve_application(app_id, notes=payload.admin_note)
    if not app:
        raise HTTPException(status_code=400, detail="Could not approve application or already processed.")

    # Notify applicant on Telegram
    user_notify_text = (
        "🎉 <b>Reseller Approved!</b>\n\n"
        "<blockquote>Status: <b>Reseller</b>\n"
        "Pricing: <b>Wholesale Rates</b>\n"
        "API Access: <b>Enabled</b></blockquote>\n\n"
        "Use /reseller to access your dashboard."
    )
    reseller_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💎 Reseller & API Hub", callback_data="open_reseller_hub")
    ]])
    await services.notifier.send_message(app["tg_user_id"], user_notify_text, reply_markup=reseller_kb)
    if getattr(services, "announcements", None):
        async def _bg_web_res_proof():
            try:
                async with services.db.connect() as rconn:
                    urow = await rconn.fetchrow("SELECT first_name, last_name, username FROM users WHERE tg_user_id = $1", app["tg_user_id"])
                fn = urow["first_name"] if urow else None
                ln = urow["last_name"] if urow else None
                un = urow["username"] if urow else None
                await services.announcements.broadcast_reseller_proof(first_name=fn, last_name=ln, username=un)
            except Exception:
                pass
        services.notifier.in_background(_bg_web_res_proof())

    return {"success": True, "message": "Application approved successfully."}


@router.post("/reseller-applications/{app_id}/reject", dependencies=WRITE)
async def reject_reseller_application(
    app_id: int,
    payload: ResellerApplicationReviewPayload,
    services: ServicesDep,
):
    reason = payload.admin_note.strip() or "Did not meet eligibility criteria at this time."
    app = await services.reseller_applications.reject_application(app_id, reason=reason)
    if not app:
        raise HTTPException(status_code=400, detail="Could not reject application or already processed.")

    # Notify applicant on Telegram
    user_notify_text = (
        "ℹ️ <b>Reseller Update</b>\n\n"
        f"<blockquote>Application: <code>#{app_id}</code>\n"
        "Status: <b>Not Approved</b></blockquote>\n\n"
        "Please contact support if you have any questions."
    )
    await services.notifier.send_message(app["tg_user_id"], user_notify_text)

    return {"success": True, "message": "Application rejected."}

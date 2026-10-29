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
        f"🎉 <b>Congratulations! Your Reseller Application has been Approved!</b>\n\n"
        f"Your account status is now upgraded to <b>Reseller</b>.\n\n"
        f"💼 <b>Benefits Activated:</b>\n"
        f"• Exclusive wholesale reseller prices on all products.\n"
        f"• Direct REST API Key access for bot/store automation.\n"
        f"• Priority automated delivery.\n\n"
        f"👉 Tap the button below or use <code>/reseller</code> to view your stats and generate your API key!"
    )
    reseller_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💎 Reseller & API Hub", callback_data="open_reseller_hub")
    ]])
    await services.notifier.send_message(app["tg_user_id"], user_notify_text, reply_markup=reseller_kb)

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
        f"ℹ️ <b>Reseller Application Update</b>\n\n"
        f"Thank you for your interest in our Reseller Program.\n"
        f"Unfortunately, your application (<b>#{app_id}</b>) was not approved at this time.\n\n"
        f"<b>Reason:</b> {reason}\n\n"
        f"If you feel this was in error or your channel has grown, you are welcome to apply again in the future or contact support."
    )
    await services.notifier.send_message(app["tg_user_id"], user_notify_text)

    return {"success": True, "message": "Application rejected."}

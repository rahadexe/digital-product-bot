from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from app.api.admin.auth import WRITE
from app.api.deps import ServicesDep

router = APIRouter()

POSTGRES_BIGINT_MAX = 2**63 - 1


@router.get("/settings")
async def read_settings(services: ServicesDep):
    # Secret settings are write-only and never returned.
    return await services.settings.public()


@router.post("/settings", dependencies=WRITE)
async def update_settings(services: ServicesDep, payload: dict[str, str] = Body(...)):
    if len(payload) > 100 or any(len(key) > 80 or len(value) > 16000 for key, value in payload.items()):
        raise HTTPException(422, "Settings exceed the supported size.")
    changed = await services.settings.update(payload)
    if any(k.startswith("binance_") for k in payload):
        await services.deposits.get_or_create_binance_method()
    return {"success": True, "changed": changed}


@router.post("/settings/test-admin-notification", dependencies=WRITE)
async def test_admin_notification(services: ServicesDep):
    chat_ids = await services.settings.admin_chat_ids()
    if not chat_ids:
        raise HTTPException(400, "No admin Telegram IDs configured. Add at least one ID first.")
    if not services.notifier.bot:
        return {
            "success": False,
            "message": "Telegram bot is running in offline mode (no active bot connection).",
            "delivered_count": 0,
            "total_admins": len(chat_ids),
            "results": [{"chat_id": cid, "delivered": False, "error": "Bot is offline"} for cid in chat_ids],
        }

    results = []
    for cid in chat_ids:
        ok = await services.notifier.send(
            cid,
            "🔔 <b>Admin Notification Test</b>\n\n"
            "This is a test notification from your Store Console.\n"
            "If you see this message, your Telegram ID is correctly configured and alerts are working! 🎉",
        )
        results.append({
            "chat_id": cid,
            "delivered": ok,
            "error": None if ok else "Could not send message. Ensure the user has started the bot (/start) and hasn't blocked it.",
        })

    delivered_count = sum(1 for r in results if r["delivered"])
    return {
        "success": delivered_count > 0,
        "delivered_count": delivered_count,
        "total_admins": len(chat_ids),
        "results": results,
    }



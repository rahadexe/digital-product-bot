from __future__ import annotations

import asyncio
import json
import logging
import secrets

from aiogram.types import Update
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("app.api.telegram")

router = APIRouter(tags=["telegram"])

MAX_BODY_BYTES = 1024 * 1024  # 1 MB
@router.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(request: Request) -> JSONResponse:
    services = request.app.state.services
    bot = services.notifier.bot
    dispatcher = getattr(services.runtime, "dispatcher", None)

    # 1. No bot or no dispatcher on services.runtime -> 404.
    if bot is None or dispatcher is None:
        return JSONResponse(status_code=404, content={"detail": "Telegram bot is not available."})

    # 2. Header X-Telegram-Bot-Api-Secret-Token compared with secrets.compare_digest; missing/wrong -> 403.
    secret_header = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if not secret_header or not secrets.compare_digest(secret_header, services.config.webhook_secret):
        return JSONResponse(status_code=403, content={"detail": "Invalid secret token."})

    # 3. Body over 1 MB -> 413 (SecurityBoundary only limits /api paths).
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_BODY_BYTES:
                return JSONResponse(status_code=413, content={"detail": "Request body is too large."})
        except ValueError:
            pass

    body = bytearray()
    try:
        async with asyncio.timeout(15):
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_BODY_BYTES:
                    return JSONResponse(status_code=413, content={"detail": "Request body is too large."})
    except TimeoutError:
        return JSONResponse(status_code=408, content={"detail": "Request timed out."})

    # 4. JSON -> Update.model_validate(data, context={"bot": bot}); invalid -> 400.
    try:
        data = json.loads(body)
        update = Update.model_validate(data, context={"bot": bot})
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Invalid update payload."})

    event = update.message or update.callback_query or update.edited_message
    sender = getattr(event, "from_user", None)
    customer_id = sender.id if sender else -update.update_id
    # Acknowledgement follows durable insertion; retries deduplicate by update ID.
    async with services.db.connect() as conn:
        await conn.execute(
            "INSERT INTO telegram_inbox(update_id,customer_id,payload) VALUES($1,$2,$3::jsonb) "
            "ON CONFLICT(update_id) DO NOTHING", update.update_id, customer_id, bytes(body).decode('utf-8'),
        )
    services.runtime.inbox_wake.set()
    return JSONResponse(status_code=200, content={"ok": True})

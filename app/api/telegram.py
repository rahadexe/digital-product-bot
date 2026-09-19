from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Any

from aiogram.types import Update
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("app.api.telegram")

router = APIRouter(tags=["telegram"])

MAX_BODY_BYTES = 1024 * 1024  # 1 MB
BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


async def _process(dispatcher: Any, bot: Any, update: Update) -> None:
    """Handle one update and log how long it took, so slow replies can be traced from the logs."""
    started = time.perf_counter()
    try:
        await dispatcher.feed_update(bot, update)
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        info_extra = ""
        if update.message:
            info_extra = f" user={update.message.from_user.id if update.message.from_user else 'None'} text={update.message.text!r}"
        elif update.callback_query:
            info_extra = f" user={update.callback_query.from_user.id if update.callback_query.from_user else 'None'} data={update.callback_query.data!r}"
        logger.info("Update %s (%s)%s handled in %.0f ms", update.update_id, update.event_type, info_extra, elapsed_ms)


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

    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"detail": "Request body is too large."})

    # 4. JSON -> Update.model_validate(data, context={"bot": bot}); invalid -> 400.
    try:
        data = json.loads(body)
        update = Update.model_validate(data, context={"bot": bot})
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Invalid update payload."})

    # Answer Telegram immediately and process in the background.
    task = asyncio.create_task(_process(dispatcher, bot, update))
    BACKGROUND_TASKS.add(task)
    if hasattr(services.runtime, "update_tasks"):
        services.runtime.update_tasks.add(task)

    def _on_done(t: asyncio.Task[Any]) -> None:
        BACKGROUND_TASKS.discard(t)
        if hasattr(services.runtime, "update_tasks"):
            services.runtime.update_tasks.discard(t)
        if not t.cancelled() and t.exception():
            logger.exception("Error processing Telegram update in background:", exc_info=t.exception())

    task.add_done_callback(_on_done)

    return JSONResponse(status_code=200, content={"ok": True})

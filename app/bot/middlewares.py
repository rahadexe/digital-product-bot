from __future__ import annotations

import asyncio

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import get_gate_keyboard
from app.services import Services

OPEN_COMMANDS = {"/start", "/menu"}


class StoreAccess(BaseMiddleware):
    """Private chats only; banned customers are stopped; force-join applies to everything except /start."""

    async def __call__(self, handler, event, data):
        services: Services = data["services"]
        user = event.from_user
        if not user:
            return None
        message = event.message if isinstance(event, CallbackQuery) else event
        # Wallet details and delivered credentials must never appear in group chats.
        if not message or message.chat.type != "private":
            if isinstance(event, CallbackQuery):
                await event.answer("Open a private chat with the bot to continue.", show_alert=True)
            return None

        opens_store = (isinstance(event, Message) and event.text and event.text.split()[0].split("@")[0] in OPEN_COMMANDS) or (
            isinstance(event, CallbackQuery) and event.data == "gate_verify"
        )
        # Both checks run on every update, so they run concurrently. /start presents the gate itself.
        if opens_store:
            record = await services.users.get(user.id)
            passed, missing = True, []
        else:
            record, (passed, missing) = await asyncio.gather(services.users.get(user.id), services.gate.check(user.id))

        if record and record["is_banned"]:
            if isinstance(event, CallbackQuery):
                await event.answer("Your account is suspended.", show_alert=True)
            else:
                await event.answer("Your account is suspended.")
            return None
        if not passed:
            if isinstance(event, CallbackQuery):
                await event.answer("Please join the required channels first.", show_alert=True)
            await message.answer(
                "Join the required channels, then verify your membership.", reply_markup=get_gate_keyboard(missing)
            )
            return None
        return await handler(event, data)

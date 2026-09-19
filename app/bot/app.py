"""Dispatcher wiring: access middleware, error handling and routers."""

from __future__ import annotations

import logging

from aiogram import Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from app.bot.handlers import admin, deposit, help_guide, profile, shop, start
from app.bot.middlewares import StoreAccess, Throttle
from app.services import Services

logger = logging.getLogger("app.bot")

HARMLESS_ERRORS = ("message is not modified", "query is too old")


async def on_error(event: ErrorEvent) -> bool:
    exc = event.exception
    if isinstance(exc, TelegramBadRequest) and any(text in str(exc).lower() for text in HARMLESS_ERRORS):
        return True
    logger.error("Unhandled bot error: %s", exc, exc_info=exc)
    return True


def create_dispatcher(services: Services, storage: BaseStorage | None = None) -> Dispatcher:
    # Handlers receive ``services`` by parameter name from the dispatcher's workflow data.
    dispatcher = Dispatcher(storage=storage or MemoryStorage(), services=services)
    # Throttling runs first, so a flood is dropped before the access checks read the database.
    throttle = Throttle()
    dispatcher.message.outer_middleware(throttle)
    dispatcher.callback_query.outer_middleware(throttle)
    access = StoreAccess()
    dispatcher.message.outer_middleware(access)
    dispatcher.callback_query.outer_middleware(access)
    dispatcher.errors.register(on_error)
    dispatcher.include_routers(admin.router, start.router, shop.router, deposit.router, profile.router, help_guide.router)
    return dispatcher

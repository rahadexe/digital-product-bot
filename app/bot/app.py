"""Dispatcher wiring: access middleware, error handling and routers."""

from __future__ import annotations

import logging

from aiogram import Dispatcher
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.types import ErrorEvent

from app.bot.handlers import admin, deposit, help_guide, navigation, profile, reseller_apply, search, shop, start
from app.bot.middlewares import AuditActor, Debounce, FastCallback, PerformanceLogger, StoreAccess, Throttle
from app.services import Services

logger = logging.getLogger("app.bot")

HARMLESS_ERRORS = ("message is not modified", "query is too old")


async def on_error(event: ErrorEvent) -> bool:
    exc = event.exception
    if isinstance(exc, TelegramBadRequest) and any(text in str(exc).lower() for text in HARMLESS_ERRORS):
        return True
    logger.error("Unhandled bot error: %s", exc, exc_info=exc)
    raise exc


def create_dispatcher(services: Services, storage: BaseStorage | None = None) -> Dispatcher:
    # Handlers receive ``services`` by parameter name from the dispatcher's workflow data.
    storage = storage or MemoryStorage()
    isolation = storage.create_isolation() if hasattr(storage, 'create_isolation') else SimpleEventIsolation()
    dispatcher = Dispatcher(storage=storage, events_isolation=isolation, services=services)
    # Track update handling speed accurately
    dispatcher.message.outer_middleware(PerformanceLogger())
    dispatcher.callback_query.outer_middleware(PerformanceLogger())
    # Instant answer for navigation buttons so Telegram spinner stops in <50ms
    dispatcher.callback_query.outer_middleware(FastCallback())
    dispatcher.message.outer_middleware(AuditActor())
    dispatcher.callback_query.outer_middleware(AuditActor())
    # Debounce drops rapid duplicate taps on the exact same button or action
    debounce = Debounce(cooldown=0.3)
    dispatcher.message.outer_middleware(debounce)
    dispatcher.callback_query.outer_middleware(debounce)
    # Throttling drops flood before access checks read the database
    throttle = Throttle()
    dispatcher.message.outer_middleware(throttle)
    dispatcher.callback_query.outer_middleware(throttle)
    access = StoreAccess()
    dispatcher.message.outer_middleware(access)
    dispatcher.callback_query.outer_middleware(access)
    # Search is armed by its button and must not outlive it: any other tap disarms it.
    end_search = search.EndSearchWhenLeaving()
    dispatcher.message.outer_middleware(end_search)
    dispatcher.callback_query.outer_middleware(end_search)
    dispatcher.errors.register(on_error)
    # search.router is last on purpose: it answers text nothing else claimed, so it must
    # never be given the chance to claim text that belongs to another handler.
    dispatcher.include_routers(navigation.router, admin.router, start.router, shop.router, deposit.router,
                               profile.router, reseller_apply.router, help_guide.router, search.router)
    return dispatcher

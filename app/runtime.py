"""Process roles: build the services once, then run the requested components until one stops."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

import uvicorn
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage

from app.core.config import Settings
from app.db.migrations import migrate
from app.services import Services, build_services

logger = logging.getLogger("app.runtime")

ROLES = ("all", "web", "worker", "migrate")
KEEP_WARM_SECONDS = 10


async def run(role: str, config: Settings) -> None:
    services = build_services(config)
    try:
        if role == "migrate" or config.auto_migrate:
            applied = await migrate(services.db)
            logger.info("Database schema is current (%d migration(s) applied).", len(applied))
        if role == "migrate":
            return

        if role in ("all", "web") and services.notifier.bot is not None:
            from app.bot.app import create_dispatcher

            services.runtime.dispatcher = create_dispatcher(services, storage=build_storage(config))

        components: list[Coroutine[Any, Any, None]] = []
        if role in ("all", "web"):
            components.append(run_web(services))

        if role in ("all", "web", "worker") and services.notifier.bot is None:
            if role == "worker":
                raise RuntimeError("The worker role needs BOT_TOKEN.")
            logger.info("BOT_TOKEN is not configured; Telegram updates and delivery are disabled.")
        else:
            if role in ("all", "web"):
                services.runtime.bot = "starting"
                if config.use_polling or not config.webhook_base_url:
                    components.append(run_polling(services))
                else:
                    components.append(run_webhook(services))
            if role in ("all", "worker"):
                components.append(run_worker(services))

        await supervise(services, components)
    finally:
        await services.close()


async def supervise(services: Services, components: list[Coroutine[Any, Any, None]]) -> None:
    tasks = [asyncio.create_task(component) for component in components]
    services.runtime.tasks.extend(tasks)
    try:
        # Components retry their own transient failures; one finishing means the process should stop.
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if not task.cancelled() and task.exception():
                raise task.exception()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def run_web(services: Services) -> None:
    from app.api.app import create_app

    config = services.config
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(services),
            host=config.host,
            port=config.port,
            log_level="info",
            access_log=False,
            # Client IP and scheme come from X-Forwarded-* only when sent by these proxies.
            proxy_headers=True,
            forwarded_allow_ips=config.trusted_proxy_ips or "127.0.0.1",
        )
    )
    logger.info("Web API listening on http://%s:%d", config.host, config.port)
    serving = asyncio.create_task(server.serve())
    try:
        await asyncio.shield(serving)
    finally:
        server.should_exit = True
        await asyncio.wait({serving}, timeout=5)


def build_storage(config: Settings) -> BaseStorage:
    """Conversation state for the bot; Redis keeps it across restarts and replicas."""
    if config.redis_url:
        from aiogram.fsm.storage.redis import RedisStorage

        return RedisStorage.from_url(config.redis_url)
    return MemoryStorage()


async def run_polling(services: Services) -> None:
    bot = services.notifier.bot
    dispatcher = services.runtime.dispatcher
    config = services.config
    if bot is None or dispatcher is None:
        return

    await services.notifier.configure_bot(config.webapp_url)

    logger.info("Starting Telegram bot in LONG POLLING mode (no webhook/tunnel needed)...")
    services.runtime.bot = "polling"
    await bot.delete_webhook(drop_pending_updates=False)

    try:
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
            handle_signals=False,
            close_bot_session=False,
        )
    finally:
        tasks = list(services.runtime.update_tasks)
        if tasks:
            logger.info("Waiting for %d in-flight update task(s) to finish...", len(tasks))
            _, pending = await asyncio.wait(tasks, timeout=5)
            for t in pending:
                t.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        if dispatcher.storage is not None:
            await dispatcher.storage.close()


async def run_webhook(services: Services) -> None:
    bot = services.notifier.bot
    dispatcher = services.runtime.dispatcher
    config = services.config
    if bot is None or dispatcher is None:
        return

    await services.notifier.configure_bot(config.webapp_url)

    backoff = 3
    while True:
        try:
            await bot.set_webhook(
                url=config.webhook_url,
                secret_token=config.webhook_secret,
                allowed_updates=dispatcher.resolve_used_update_types(),
                drop_pending_updates=False,
                max_connections=40,
            )
            services.runtime.bot = "webhook"
            logger.info("Telegram webhook configured: %s", config.webhook_url)
            break
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to configure Telegram webhook; retrying in %d seconds.", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    try:
        while True:
            # aiohttp closes a connection after 15 idle seconds, so the first reply after a quiet spell would
            # wait for a new TCP and TLS handshake with Telegram (several round trips away from Europe).
            # A light call every few seconds keeps one connection open for real replies.
            await asyncio.sleep(KEEP_WARM_SECONDS)
            try:
                await bot.get_me()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
    finally:
        tasks = list(services.runtime.update_tasks)
        if tasks:
            logger.info("Waiting for %d in-flight update task(s) to finish...", len(tasks))
            _, pending = await asyncio.wait(tasks, timeout=5)
            for t in pending:
                t.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        if dispatcher.storage is not None:
            await dispatcher.storage.close()


async def run_worker(services: Services) -> None:
    from app.workers.delivery import DeliveryWorker
    from app.workers.payments import PaymentWatcher

    await asyncio.gather(DeliveryWorker(services.delivery, services.notifier.bot).run(), PaymentWatcher(services).run())

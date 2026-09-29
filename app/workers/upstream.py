"""Background worker for periodic upstream supplier health check, low balance alert and catalog sync."""

from __future__ import annotations

import asyncio
import logging

from app.services import Services

logger = logging.getLogger("app.workers.upstream")

CHECK_INTERVAL_SECONDS = 1800  # Every 30 minutes


class UpstreamWorker:
    def __init__(self, services: Services):
        self.services = services

    async def run(self) -> None:
        logger.info("Upstream supplier worker started.")
        # Initial sleep on startup to let app initialize smoothly
        await asyncio.sleep(10)
        while True:
            try:
                reseller = self.services.upstream_reseller
                if reseller and reseller.is_configured:
                    # 1. Check low balance alert
                    try:
                        await reseller.check_low_balance(self.services.notifier)
                    except Exception as exc:
                        logger.warning("Upstream balance check failed: %s", exc)

                    # 2. Check if auto-sync is enabled
                    try:
                        auto_sync = await self.services.settings.flag("upstream_auto_sync")
                        if auto_sync:
                            cats, prods = await reseller.sync_catalog()
                            if prods > 0:
                                logger.info("Upstream auto-sync completed: %d products, %d categories.", prods, cats)
                    except Exception as exc:
                        logger.warning("Upstream auto-sync failed: %s", exc)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Unexpected error in upstream worker loop.")

            try:
                await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break

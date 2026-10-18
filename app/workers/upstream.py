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

    async def check_once(self) -> None:
        manager = self.services.suppliers
        for supplier in manager.list_all():
            try:
                await supplier._ensure_config()
                if not supplier.is_configured:
                    continue
                await supplier.check_low_balance(self.services.notifier)
            except Exception:
                logger.warning("Supplier balance check failed for %s.", supplier.code)
            try:
                prefix = "upstream" if supplier.code == "digital_mart" else supplier.code
                if supplier.is_configured and await self.services.settings.flag(f"{prefix}_auto_sync"):
                    cats, prods = await supplier.sync_catalog()
                    catalog = getattr(self.services, "catalog", None)
                    if catalog:
                        catalog.invalidate()
                    logger.info("Supplier %s synced %d products, %d categories.", supplier.code, prods, cats)
            except Exception:
                logger.warning("Supplier catalog sync failed for %s.", supplier.code)

    async def run(self) -> None:
        logger.info("Upstream supplier worker started.")
        # Initial sleep on startup to let app initialize smoothly
        await asyncio.sleep(10)
        while True:
            try:
                await self.check_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Unexpected error in upstream worker loop.")

            try:
                await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break

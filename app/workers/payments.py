"""Checks payments nobody is watching: unpaid ZiniPay invoices and USDT deposits awaiting Binance.

A missed callback, a closed Mini App or a transaction that confirms minutes later still credits the
wallet without anyone touching it."""

from __future__ import annotations

import asyncio
import logging

from app.services import Services

logger = logging.getLogger("app.workers.payments")

INTERVAL_SECONDS = 60


class PaymentWatcher:
    def __init__(self, services: Services):
        self.services = services

    async def run(self) -> None:
        while True:
            try:
                await self.services.payments.recheck_pending()
                await self.services.binance.recheck_pending()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Checking pending payments failed; retrying later.")
            await asyncio.sleep(INTERVAL_SECONDS)

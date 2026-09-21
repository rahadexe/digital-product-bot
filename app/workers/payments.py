"""Checks payments nobody is watching: unpaid ZiniPay invoices and USDT deposits awaiting Binance.

A missed callback, a closed Mini App or a transaction that confirms minutes later still credits the
wallet without anyone touching it."""

from __future__ import annotations

import asyncio
import logging
import time

from app.services import Services

logger = logging.getLogger("app.workers.payments")

INTERVAL_SECONDS = 60


class PaymentWatcher:
    def __init__(self, services: Services):
        self.services = services
        self.last_cleanup = 0.0

    async def run(self) -> None:
        while True:
            try:
                for check in (self.services.zinipay.recover, self.services.payments.recheck_pending, self.services.binance.recheck_pending):
                    try:
                        await check()
                    except Exception:
                        logger.exception("A payment checker failed; continuing with the remaining gateways.")
                if time.monotonic() - self.last_cleanup > 3600:
                    await self.cleanup()
                    self.last_cleanup = time.monotonic()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Checking pending payments failed; retrying later.")
            await asyncio.sleep(INTERVAL_SECONDS)

    async def cleanup(self) -> None:
        # Financial history and unfinished jobs are never pruned here.
        async with self.services.db.transaction() as conn:
            await conn.execute("DELETE FROM request_limits WHERE expires_at<now()-interval '1 day'")
            await conn.execute("DELETE FROM verification_limits WHERE expires_at<now()-interval '1 day'")
            await conn.execute("DELETE FROM admin_login_attempts WHERE attempted_at<now()-interval '1 day'")
            await conn.execute("DELETE FROM revoked_admin_sessions WHERE expires_at<$1", int(time.time()))
            await conn.execute("DELETE FROM telegram_inbox WHERE status='done' AND created_at<now()-interval '7 days'")
            await conn.execute("DELETE FROM bot_conversations WHERE state IS NULL AND updated_at<now()-interval '7 days'")

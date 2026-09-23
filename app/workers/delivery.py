"""Sends queued receipts and broadcasts. Any number of workers may run; each claims different rows."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import (
    BufferedInputFile,
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from app.bot.icons import Icons
from app.services.delivery import DeliveryService

logger = logging.getLogger("app.workers.delivery")

MAX_ATTEMPTS = 5
TELEGRAM_TEXT_LIMIT = 4000


class DeliveryWorker:
    def __init__(self, delivery: DeliveryService, bot: Bot):
        self.delivery = delivery
        self.bot = bot

    async def run(self) -> None:
        await self.delivery.recover_missing_receipts()
        while True:
            try:
                if not await self.step():
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                raise
            except Exception:
                # A network database can drop connections; a claimed row is retried after its lease.
                logger.exception("Outbox delivery step failed; retrying shortly.")
                await asyncio.sleep(5)

    async def step(self) -> bool:
        """Deliver one due message. Returns False when nothing was due."""
        message = await self.delivery.claim_next()
        if not message:
            return False
        order = await self.delivery.order_for(message) if message['order_id'] else None
        if message['order_id'] and (not order or order['status'] == 'refunded'):
            await self.delivery.cancel(message)
            return True
        # "Being prepared" is pointless, and confusing, once that order has been refunded.
        if message.get('about_order_id'):
            about = await self.delivery.order_for({'order_id': message['about_order_id'], 'tg_user_id': message['tg_user_id']})
            if not about or about['status'] == 'refunded':
                await self.delivery.cancel(message)
                return True

        status, delay, error = 'sent', 0.0, ''
        try:
            if len(message['text']) > TELEGRAM_TEXT_LIMIT:
                # Long credentials must remain one intact, downloadable item.
                content = order['delivered_item'] if order else message['text']
                await self.bot.send_document(
                    message['tg_user_id'],
                    BufferedInputFile(content.encode(), filename=f"order-{message['order_id']}.txt"),
                )
            else:
                reply_markup = None
                if order and order.get('delivered_item') and len(order['delivered_item']) <= 256:
                    reply_markup = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [InlineKeyboardButton(text="Copy Credentials", copy_text=CopyTextButton(text=order['delivered_item']), style="success", icon_custom_emoji_id=Icons.KEY)]
                        ]
                    )
                await self.bot.send_message(message['tg_user_id'], message['text'], reply_markup=reply_markup)
        except TelegramRetryAfter as exc:
            status, delay, error = 'pending', exc.retry_after + 1, 'Telegram rate limit'
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            status, error = 'failed', type(exc).__name__
        except Exception as exc:
            # attempts already counts this send.
            status = 'failed' if message['attempts'] >= MAX_ATTEMPTS else 'pending'
            delay, error = min(300, 2 ** (message['attempts'] + 1)), type(exc).__name__
        await self.delivery.finish(message, status, delay, error)
        await asyncio.sleep(0.06)  # Retry-After is persisted on the message; other recipients can proceed.
        return True

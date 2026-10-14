"""Mandatory channel membership (force-join) and the channels it requires."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Any

from aiogram.exceptions import TelegramRetryAfter

from app.db import Database, affected
from app.services.audit import record
from app.services.notifications import Notifier
from app.services.settings import SettingsService

logger = logging.getLogger("app.services.gate")

CHANNEL_FIELDS = ("channel_username", "chat_id", "title", "invite_link", "is_active")
# Every bot update is gated, so a confirmed membership is reused instead of calling Telegram each time.
# A customer who leaves a channel keeps access for at most this long.
MEMBERSHIP_CACHE_SECONDS = 300.0
MEMBERSHIP_CACHE_SIZE = 10000
FAILED_CHECK_CACHE_SECONDS = 2.0
MEMBERSHIP_TIMEOUT_SECONDS = 4.0


class GateService:
    CACHE_SECONDS = 30.0

    def __init__(self, db: Database, settings: SettingsService, notifier: Notifier):
        self.db = db
        self.settings = settings
        self.notifier = notifier
        self._active: tuple[float, list[dict[str, Any]]] | None = None
        self._verified: OrderedDict[int, float] = OrderedDict()
        self._last_channel_alert: dict[str, float] = {}
        self._missing: OrderedDict[int, tuple[float, list[dict[str, Any]]]] = OrderedDict()
        self._checks: dict[int, asyncio.Task] = {}
        self._membership_slots = asyncio.Semaphore(32)
        self._unavailable: OrderedDict[str, tuple[float, str]] = OrderedDict()

    def _invalidate(self) -> None:
        self._active = None
        self._verified.clear()
        self._missing.clear()
        self._checks.clear()
        self._unavailable.clear()

    def forget(self, tg_user_id: int) -> None:
        """Drop a confirmed membership, so the next update is checked against Telegram again.

        Telegram reports a customer leaving a channel the moment it happens, which is far
        better than waiting out the cache. Calling this on that report closes the window in
        which someone can join, get in, leave, and keep browsing.
        """
        self._verified.pop(tg_user_id, None)
        self._missing.pop(tg_user_id, None)
        self._checks.pop(tg_user_id, None)

    async def guards(self, chat_id: int, username: str | None) -> bool:
        """Whether this chat is one of the channels customers must join."""
        wanted = {str(chat_id)}
        if username:
            wanted |= {username.lower(), f"@{username.lower()}"}
        for channel in await self.channels():
            for field in ("chat_id", "channel_username"):
                value = str(channel.get(field) or "").strip().lower()
                if value and value in wanted:
                    return True
        return False

    async def channels(self, active_only: bool = True) -> list[dict[str, Any]]:
        now = time.monotonic()
        if active_only and self._active and now - self._active[0] < self.CACHE_SECONDS:
            return [dict(row) for row in self._active[1]]
        query = "SELECT * FROM gate_channels" + (" WHERE is_active = 1" if active_only else "") + " ORDER BY id"
        async with self.db.connect() as conn:
            rows = [dict(row) for row in await conn.fetch(query)]
        if active_only:
            if self._active is not None and self._active[1] != rows:
                self._invalidate()
            self._active = (now, rows)
        return [dict(row) for row in rows]

    async def add(self, channel_username: str, title: str, invite_link: str, chat_id: str = "", is_active: int = 1) -> int:
        async with self.db.transaction() as conn:
            channel_id = await conn.fetchval(
                "INSERT INTO gate_channels (channel_username, chat_id, title, invite_link, is_active) "
                "VALUES ($1, $2, $3, $4, $5) RETURNING id",
                channel_username.strip(),
                chat_id.strip(),
                title.strip(),
                invite_link.strip(),
                is_active,
            )
            await record(conn, "gate_channel_added", f"Channel #{channel_id}: {channel_username}")
        self._invalidate()
        return channel_id

    async def update(self, channel_id: int, **fields: Any) -> bool:
        updates = {key: value for key, value in fields.items() if key in CHANNEL_FIELDS}
        if not updates:
            return False
        columns = ", ".join(f"{key} = ${index}" for index, key in enumerate(updates, start=1))
        async with self.db.transaction() as conn:
            status = await conn.execute(
                f"UPDATE gate_channels SET {columns} WHERE id = ${len(updates) + 1}", *updates.values(), channel_id
            )
            if affected(status):
                await record(conn, "gate_channel_updated", f"Channel #{channel_id}")
        self._invalidate()
        return bool(affected(status))

    async def remove(self, channel_id: int) -> None:
        async with self.db.transaction() as conn:
            if affected(await conn.execute("DELETE FROM gate_channels WHERE id = $1", channel_id)):
                await record(conn, "gate_channel_removed", f"Channel #{channel_id}")
        self._invalidate()

    async def check(self, tg_user_id: int) -> tuple[bool, list[dict[str, Any]]]:
        """Whether the customer joined every active channel. Unverifiable membership counts as missing."""
        if not await self.settings.flag("force_join_enabled"):
            return True, []
        channels = [dict(ch) for ch in await self.channels()]
        if not channels:
            return True, []

        now = time.monotonic()
        verified_at = self._verified.get(tg_user_id)
        if verified_at is not None and now - verified_at < MEMBERSHIP_CACHE_SECONDS:
            return True, []

        cached = self._missing.get(tg_user_id)
        if cached and now - cached[0] < FAILED_CHECK_CACHE_SECONDS:
            return False, [dict(ch) for ch in cached[1]]

        task = self._checks.get(tg_user_id)
        if task is None:
            task = asyncio.create_task(self._check_channels(tg_user_id, channels))
            self._checks[tg_user_id] = task
            task.add_done_callback(lambda finished: self._finish_check(tg_user_id, finished))
        # A cancelled HTTP/update waiter must not cancel the shared verification.
        missing = await asyncio.shield(task)
        return not missing, [dict(ch) for ch in missing]

    def _finish_check(self, tg_user_id: int, task: asyncio.Task) -> None:
        if task.cancelled():
            if self._checks.get(tg_user_id) is task:
                self._checks.pop(tg_user_id, None)
            return
        error = task.exception()
        if self._checks.get(tg_user_id) is task:
            self._checks.pop(tg_user_id, None)
            if error is not None:
                return
            missing = task.result()
            if missing:
                self._verified.pop(tg_user_id, None)
                self._missing[tg_user_id] = (time.monotonic(), missing)
                self._missing.move_to_end(tg_user_id)
                while len(self._missing) > MEMBERSHIP_CACHE_SIZE:
                    self._missing.popitem(last=False)
            else:
                self.grant_access(tg_user_id)

    async def _check_channels(self, tg_user_id: int, channels: list[dict[str, Any]]) -> list[dict[str, Any]]:
        async def _check_one(channel: dict[str, Any]) -> bool:
            target = channel.get("chat_id") or channel.get("channel_username")
            cooldown = self._unavailable.get(str(target))
            if cooldown and time.monotonic() < cooldown[0]:
                channel['verification_unavailable'] = True
                channel['error_reason'] = cooldown[1]
                return False
            try:
                async with asyncio.timeout(MEMBERSHIP_TIMEOUT_SECONDS):
                    async with self._membership_slots:
                        return bool(target) and await self.notifier.is_member(target, tg_user_id)
            except Exception as exc:
                channel["verification_unavailable"] = True
                channel["error_reason"] = f"{type(exc).__name__}: {exc}"
                delay = max(5.0, float(exc.retry_after)) if isinstance(exc, TelegramRetryAfter) else 5.0
                self._unavailable[str(target)] = (time.monotonic() + delay, channel['error_reason'])
                self._unavailable.move_to_end(str(target))
                while len(self._unavailable) > MEMBERSHIP_CACHE_SIZE:
                    self._unavailable.popitem(last=False)
                logger.warning("Gate verification unavailable for %s: %s", target, type(exc).__name__)
                return False

        results = await asyncio.gather(*(_check_one(ch) for ch in channels))
        # strict: a result missing for any channel must fail loudly rather than silently
        # letting a customer through a channel that was never checked.
        return [ch for ch, ok in zip(channels, results, strict=True) if not ok]

    def grant_access(self, tg_user_id: int) -> None:
        """Cache a successfully verified membership."""
        now = time.monotonic()
        self._missing.pop(tg_user_id, None)
        self._verified[tg_user_id] = now
        self._verified.move_to_end(tg_user_id)
        while len(self._verified) > MEMBERSHIP_CACHE_SIZE:
            self._verified.popitem(last=False)

    async def notify_admin_channel_issue(self, errored: list[dict[str, Any]], user: Any = None) -> None:
        """Send a high-priority alert to bot administrators when a channel check fails due to bot/channel error."""
        now = time.monotonic()
        channels_to_alert = []
        for ch in errored:
            target = str(ch.get("chat_id") or ch.get("channel_username") or ch.get("title") or "")
            last_alert = self._last_channel_alert.get(target, 0.0)
            if now - last_alert >= 900.0:  # 15 minutes throttle per channel
                self._last_channel_alert[target] = now
                channels_to_alert.append(ch)

        if not channels_to_alert:
            return

        from html import escape

        user_info = ""
        if user:
            name = getattr(user, "full_name", "") or getattr(user, "first_name", "") or "Customer"
            uid = getattr(user, "id", None)
            user_info = f"\n\n👤 <b>User:</b> {escape(str(name))} (ID: <code>{uid}</code>)"

        lines = [
            "⚠️ <b>Force Join Gate Alert</b>",
            "",
            "The bot could not verify membership for the required channel(s):",
        ]
        for ch in channels_to_alert:
            target = ch.get("chat_id") or ch.get("channel_username") or "Unknown"
            title = ch.get("title") or target
            reason = ch.get("error_reason") or "Bot might not be an admin in this channel"
            lines.append(f"• <b>{escape(str(title))}</b> (<code>{escape(str(target))}</code>)\n  <i>Error: {escape(str(reason))}</i>")

        lines.append("\n🔒 <b>Action taken:</b> Unverified users are asked to retry; membership access remains locked.")
        lines.append("👉 <i>Please ensure the bot is added as an administrator with invite/member permissions in the channel.</i>")
        if user_info:
            lines.append(user_info)

        text = "\n".join(lines)
        try:
            await self.notifier.send_admin(text)
        except Exception as exc:
            logger.error("Failed to send gate channel alert to admin: %s", exc)


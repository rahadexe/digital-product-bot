"""Mandatory channel membership (force-join) and the channels it requires."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Any

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


class GateService:
    CACHE_SECONDS = 30.0

    def __init__(self, db: Database, settings: SettingsService, notifier: Notifier):
        self.db = db
        self.settings = settings
        self.notifier = notifier
        self._active: tuple[float, list[dict[str, Any]]] | None = None
        self._verified: OrderedDict[int, float] = OrderedDict()

    def _invalidate(self) -> None:
        self._active = None
        self._verified.clear()

    def forget(self, tg_user_id: int) -> None:
        """Drop a confirmed membership, so the next update is checked against Telegram again.

        Telegram reports a customer leaving a channel the moment it happens, which is far
        better than waiting out the cache. Calling this on that report closes the window in
        which someone can join, get in, leave, and keep browsing.
        """
        self._verified.pop(tg_user_id, None)

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
        channels = await self.channels()
        if not channels:
            return True, []

        now = time.monotonic()
        verified_at = self._verified.get(tg_user_id)
        if verified_at is not None and now - verified_at < MEMBERSHIP_CACHE_SECONDS:
            return True, []

        missing = []
        async def _check_one(channel: dict[str, Any]) -> bool:
            target = channel.get("chat_id") or channel.get("channel_username")
            try:
                if not target or not await self.notifier.is_member(target, tg_user_id):
                    return False
                return True
            except Exception as exc:
                logger.warning("Gate verification unavailable for %s: %s", target, type(exc).__name__)
                return False

        results = await asyncio.gather(*(_check_one(ch) for ch in channels))
        # strict: a result missing for any channel must fail loudly rather than silently
        # letting a customer through a channel that was never checked.
        missing = [ch for ch, ok in zip(channels, results, strict=True) if not ok]

        if missing:
            self._verified.pop(tg_user_id, None)
        else:
            self._verified[tg_user_id] = now
            self._verified.move_to_end(tg_user_id)
            while len(self._verified) > MEMBERSHIP_CACHE_SIZE:
                self._verified.popitem(last=False)
        return not missing, missing

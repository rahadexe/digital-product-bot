"""Channels customers see under the 📢 Channel menu, each opened by its own link button."""

from __future__ import annotations

import time
from typing import Any

from app.db import Database, affected
from app.services.audit import record

CHANNEL_FIELDS = ("title", "url", "sort_order", "is_active")


def channel_url(raw: str) -> str:
    """A t.me link from @username, t.me/..., or a full link."""
    raw = raw.strip()
    if raw.startswith(("https://", "http://")):
        return raw
    if raw.startswith(("t.me/", "telegram.me/")):
        return f"https://{raw}"
    return f"https://t.me/{raw.lstrip('@')}"


class UpdateChannelService:
    CACHE_SECONDS = 30.0

    def __init__(self, db: Database):
        self.db = db
        self._active: tuple[float, list[dict[str, Any]]] | None = None

    async def channels(self, active_only: bool = True) -> list[dict[str, Any]]:
        now = time.monotonic()
        if active_only and self._active and now - self._active[0] < self.CACHE_SECONDS:
            return [dict(row) for row in self._active[1]]
        query = "SELECT * FROM update_channels" + (" WHERE is_active = 1" if active_only else "") + " ORDER BY sort_order, id"
        async with self.db.connect() as conn:
            rows = [dict(row) for row in await conn.fetch(query)]
        if active_only:
            self._active = (now, rows)
        return [dict(row) for row in rows]

    async def add(self, title: str, url: str, sort_order: int = 0, is_active: int = 1) -> int:
        async with self.db.transaction() as conn:
            channel_id = await conn.fetchval(
                "INSERT INTO update_channels (title, url, sort_order, is_active) VALUES ($1, $2, $3, $4) RETURNING id",
                title.strip(),
                channel_url(url),
                sort_order,
                is_active,
            )
            await record(conn, "update_channel_added", f"Channel #{channel_id}: {title.strip()}")
        self._active = None
        return channel_id

    async def update(self, channel_id: int, **fields: Any) -> bool:
        updates = {key: value for key, value in fields.items() if key in CHANNEL_FIELDS}
        if "url" in updates:
            updates["url"] = channel_url(updates["url"])
        if not updates:
            return False
        columns = ", ".join(f"{key} = ${index}" for index, key in enumerate(updates, start=1))
        async with self.db.transaction() as conn:
            status = await conn.execute(
                f"UPDATE update_channels SET {columns} WHERE id = ${len(updates) + 1}", *updates.values(), channel_id
            )
            if affected(status):
                await record(conn, "update_channel_updated", f"Channel #{channel_id}")
        self._active = None
        return bool(affected(status))

    async def remove(self, channel_id: int) -> None:
        async with self.db.transaction() as conn:
            if affected(await conn.execute("DELETE FROM update_channels WHERE id = $1", channel_id)):
                await record(conn, "update_channel_removed", f"Channel #{channel_id}")
        self._active = None

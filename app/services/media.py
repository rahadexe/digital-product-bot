"""Images the admin uploads for the storefront, stored in the database: the Mini App home banners."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any

from app.db import Database, affected
from app.services.audit import record
from app.services.errors import InvalidInputError

# Banners are shown at a fixed 12:5 ratio on every screen, so this size fills them exactly.
BANNER_RECOMMENDED = {"width": 1200, "height": 500}
MAX_BANNERS = 5
MAX_IMAGE_BYTES = 900 * 1024
MAX_DIMENSION = 6000


@dataclass(frozen=True)
class ImageInfo:
    content_type: str
    width: int
    height: int


def image_info(data: bytes) -> ImageInfo | None:
    """Type and size read from the file's own header; the type the uploader claims is never trusted."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR" and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return ImageInfo("image/png", width, height)
    if data[:3] == b"\xff\xd8\xff":
        return _jpeg_info(data)
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return _webp_info(data)
    return None


def _jpeg_info(data: bytes) -> ImageInfo | None:
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker == 0xFF:
            index += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            index += 2
            continue
        length = struct.unpack(">H", data[index + 2 : index + 4])[0]
        # Start-of-frame segments carry the dimensions; C4, C8 and CC share the range but are not frames.
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[index + 5 : index + 9])
            return ImageInfo("image/jpeg", width, height)
        index += 2 + length
    return None


def _webp_info(data: bytes) -> ImageInfo | None:
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
    elif chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
        width, height = (value & 0x3FFF for value in struct.unpack("<HH", data[26:30]))
    elif chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        bits = int.from_bytes(data[21:25], "little")
        width, height = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    else:
        return None
    return ImageInfo("image/webp", width, height)


def _validated(data: bytes) -> ImageInfo:
    if not data:
        raise InvalidInputError("Choose an image to upload.")
    if len(data) > MAX_IMAGE_BYTES:
        raise InvalidInputError("The image is larger than 900 KB. Export it at 1200 × 500 px as JPG or WebP.")
    info = image_info(data)
    if info is None:
        raise InvalidInputError("Upload a JPG, PNG or WebP image.")
    if not (0 < info.width <= MAX_DIMENSION and 0 < info.height <= MAX_DIMENSION):
        raise InvalidInputError(f"The image must be at most {MAX_DIMENSION} px on each side.")
    return info


def _meta(row: Any) -> dict[str, Any]:
    version = int(row["created_at"].timestamp() * 1000)
    return {
        "id": row["id"],
        # Versioned, so a browser can keep its copy for as long as it likes.
        "url": f"/media/banners/{row['id']}?v={version}",
        "width": row["width"],
        "height": row["height"],
        "size": row["size"],
        "content_type": row["content_type"],
        "created_at": row["created_at"].isoformat(),
    }


class MediaService:
    def __init__(self, db: Database):
        self.db = db

    async def banners(self) -> list[dict[str, Any]]:
        """Every home banner in display order, without loading the images themselves."""
        async with self.db.connect() as conn:
            rows = await conn.fetch(
                "SELECT id, content_type, width, height, octet_length(data) AS size, created_at "
                "FROM home_banners ORDER BY position, id"
            )
        return [_meta(row) for row in rows]

    async def banner_image(self, banner_id: int) -> tuple[bytes, str, int] | None:
        async with self.db.connect() as conn:
            row = await conn.fetchrow("SELECT data, content_type, created_at FROM home_banners WHERE id = $1", banner_id)
        if not row:
            return None
        return bytes(row["data"]), row["content_type"], int(row["created_at"].timestamp() * 1000)

    async def add_banner(self, data: bytes) -> dict[str, Any]:
        info = _validated(data)
        async with self.db.transaction() as conn:
            # One upload at a time, so two admins cannot both add the sixth banner.
            await conn.execute("LOCK TABLE home_banners IN SHARE ROW EXCLUSIVE MODE")
            existing = await conn.fetchrow("SELECT count(*) AS count, COALESCE(max(position), -1) AS last FROM home_banners")
            if existing["count"] >= MAX_BANNERS:
                raise InvalidInputError(f"You can show up to {MAX_BANNERS} banners. Remove one before adding another.")
            row = await conn.fetchrow(
                "INSERT INTO home_banners (position, content_type, data, width, height) VALUES ($1, $2, $3, $4, $5) "
                "RETURNING id, content_type, width, height, octet_length(data) AS size, created_at",
                existing["last"] + 1,
                info.content_type,
                data,
                info.width,
                info.height,
            )
            await record(
                conn,
                "banner_added",
                f"Home banner #{row['id']} {info.width}x{info.height} {info.content_type}, {len(data)} bytes",
            )
        return _meta(row)

    async def remove_banner(self, banner_id: int) -> bool:
        async with self.db.transaction() as conn:
            removed = affected(await conn.execute("DELETE FROM home_banners WHERE id = $1", banner_id))
            if removed:
                await record(conn, "banner_removed", f"Home banner #{banner_id} removed")
        return bool(removed)

    async def get_welcome_banner(self) -> tuple[bytes, str, int, int, int] | None:
        """Returns (data, content_type, width, height, version_timestamp) or None."""
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                "SELECT data, content_type, width, height, updated_at FROM bot_welcome_banners WHERE id = 1"
            )
        if not row:
            return None
        return (
            bytes(row["data"]),
            row["content_type"],
            row["width"],
            row["height"],
            int(row["updated_at"].timestamp() * 1000),
        )

    async def set_welcome_banner(self, data: bytes) -> dict[str, Any]:
        if not data:
            raise InvalidInputError("Choose an image to upload.")
        if len(data) > 5 * 1024 * 1024:
            raise InvalidInputError("The image is larger than 5 MB. Please upload a smaller JPG, PNG, or WebP.")
        info = image_info(data)
        if info is None:
            raise InvalidInputError("Upload a valid JPG, PNG, or WebP image.")
        if not (0 < info.width <= MAX_DIMENSION and 0 < info.height <= MAX_DIMENSION):
            raise InvalidInputError(f"The image must be at most {MAX_DIMENSION} px on each side.")

        async with self.db.transaction() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO bot_welcome_banners (id, content_type, data, width, height, updated_at)
                VALUES (1, $1, $2, $3, $4, now())
                ON CONFLICT (id) DO UPDATE
                SET content_type = EXCLUDED.content_type,
                    data = EXCLUDED.data,
                    width = EXCLUDED.width,
                    height = EXCLUDED.height,
                    updated_at = now()
                RETURNING id, content_type, width, height, octet_length(data) AS size, updated_at
                """,
                info.content_type,
                data,
                info.width,
                info.height,
            )
            version = int(row["updated_at"].timestamp() * 1000)
            url = f"/media/welcome-banner?v={version}"
            await conn.execute(
                "INSERT INTO bot_settings (key, value) VALUES ('notice_banner', $1) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                url,
            )
            await record(
                conn,
                "welcome_banner_updated",
                f"Bot welcome banner updated: {info.width}x{info.height} {info.content_type}, {len(data)} bytes",
            )
        return {
            "url": url,
            "width": row["width"],
            "height": row["height"],
            "size": row["size"],
            "content_type": row["content_type"],
        }

    async def remove_welcome_banner(self) -> bool:
        async with self.db.transaction() as conn:
            removed = affected(await conn.execute("DELETE FROM bot_welcome_banners WHERE id = 1"))
            await conn.execute(
                "INSERT INTO bot_settings (key, value) VALUES ('notice_banner', '') "
                "ON CONFLICT (key) DO UPDATE SET value = ''"
            )
            if removed:
                await record(conn, "welcome_banner_removed", "Bot welcome banner removed")
        return bool(removed)



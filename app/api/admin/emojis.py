from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.admin.auth import WRITE
from app.api.deps import ServicesDep
from app.services.audit import record

router = APIRouter()

# Protected system presets (built-in and cannot be deleted or modified)
SYSTEM_EMOJIS: list[dict[str, Any]] = [
    {"name": "NordVPN", "emoji_id": "5796345694969140339", "is_system": True},
    {"name": "ExpressVPN", "emoji_id": "5796153709931009517", "is_system": True},
    {"name": "Surfshark", "emoji_id": "5796592771552777710", "is_system": True},
    {"name": "Proton VPN", "emoji_id": "5794298344188678751", "is_system": True},
    {"name": "CyberGhost", "emoji_id": "5796309230696797985", "is_system": True},
    {"name": "HMA VPN", "emoji_id": "5796595022115639741", "is_system": True},
    {"name": "Bitdefender", "emoji_id": "5793973558761756143", "is_system": True},
    {"name": "Windscribe", "emoji_id": "5794045349140108622", "is_system": True},
    {"name": "PureVPN", "emoji_id": "5794156713347126602", "is_system": True},
    {"name": "Turbo VPN", "emoji_id": "5796633857209931262", "is_system": True},
    {"name": "PotatoVPN", "emoji_id": "5796403831646458962", "is_system": True},
    {"name": "PandaVPN", "emoji_id": "5796561774773801876", "is_system": True},
    {"name": "IPVanish", "emoji_id": "5796381996032725483", "is_system": True},
    {"name": "X VPN", "emoji_id": "5794376731636798062", "is_system": True},
    {"name": "bKash", "emoji_id": "6217678000977089090", "is_system": True},
    {"name": "Nagad", "emoji_id": "6217625168584380551", "is_system": True},
    {"name": "Rocket", "emoji_id": "4911601033496494993", "is_system": True},
    {"name": "Binance", "emoji_id": "5348212415077064131", "is_system": True},
    {"name": "Bybit", "emoji_id": "5348372939479751825", "is_system": True},
]


class EmojiCreatePayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    emoji_id: str = Field(..., min_length=1, max_length=50)


@router.get("/emojis")
async def list_emojis(services: ServicesDep):
    async with services.db.connect() as conn:
        rows = await conn.fetch("SELECT id, name, emoji_id, created_at FROM custom_emojis ORDER BY id DESC")

    custom_emojis = [
        {
            "id": row["id"],
            "name": row["name"],
            "emoji_id": row["emoji_id"],
            "is_system": False,
            "created_at": row["created_at"].isoformat() if row["created_at"] else "",
        }
        for row in rows
    ]

    all_emojis = [*custom_emojis, *SYSTEM_EMOJIS]
    return {
        "system": SYSTEM_EMOJIS,
        "custom": custom_emojis,
        "all": all_emojis,
    }


@router.post("/emojis", dependencies=WRITE)
async def create_emoji(payload: EmojiCreatePayload, services: ServicesDep):
    name = payload.name.strip()
    raw_emoji_id = payload.emoji_id.strip()

    # Extract digits only if full tag or spaces pasted
    cleaned_id = re.sub(r"\D", "", raw_emoji_id)
    if not cleaned_id:
        raise HTTPException(status_code=400, detail="Emoji ID must contain numbers.")

    # Check if this ID is already in system emojis
    if any(s["emoji_id"] == cleaned_id for s in SYSTEM_EMOJIS):
        raise HTTPException(status_code=400, detail="This emoji ID already exists in the system library.")

    async with services.db.transaction() as conn:
        row_id = await conn.fetchval(
            """
            INSERT INTO custom_emojis (name, emoji_id)
            VALUES ($1, $2)
            ON CONFLICT (emoji_id) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            name,
            cleaned_id,
        )
        await record(conn, "emoji_created", f"Added custom emoji '{name}' ({cleaned_id})")

    return {"success": True, "id": row_id}


@router.delete("/emojis/{emoji_id}", dependencies=WRITE)
async def delete_emoji(emoji_id: str, services: ServicesDep):
    clean = emoji_id.strip()
    if any(s["emoji_id"] == clean for s in SYSTEM_EMOJIS):
        raise HTTPException(status_code=400, detail="Built-in system emojis cannot be deleted.")

    async with services.db.transaction() as conn:
        if clean.isdigit():
            # Try deleting by db id or by emoji_id
            deleted = await conn.execute(
                "DELETE FROM custom_emojis WHERE id = $1 OR emoji_id = $2",
                int(clean),
                clean,
            )
        else:
            deleted = await conn.execute("DELETE FROM custom_emojis WHERE emoji_id = $1", clean)

        await record(conn, "emoji_deleted", f"Removed custom emoji ID '{clean}'")

    return {"success": True, "deleted": deleted.endswith("1")}

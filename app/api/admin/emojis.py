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
    # VPN Services
    {"name": "NordVPN", "emoji_id": "5796345694969140339", "category": "VPN", "is_system": True},
    {"name": "ExpressVPN", "emoji_id": "5796153709931009517", "category": "VPN", "is_system": True},
    {"name": "Surfshark", "emoji_id": "5796592771552777710", "category": "VPN", "is_system": True},
    {"name": "Proton VPN", "emoji_id": "5794298344188678751", "category": "VPN", "is_system": True},
    {"name": "CyberGhost", "emoji_id": "5796309230696797985", "category": "VPN", "is_system": True},
    {"name": "HMA VPN", "emoji_id": "5796595022115639741", "category": "VPN", "is_system": True},
    {"name": "Bitdefender", "emoji_id": "5793973558761756143", "category": "VPN", "is_system": True},
    {"name": "Windscribe", "emoji_id": "5794045349140108622", "category": "VPN", "is_system": True},
    {"name": "PureVPN", "emoji_id": "5794156713347126602", "category": "VPN", "is_system": True},
    {"name": "Turbo VPN", "emoji_id": "5796633857209931262", "category": "VPN", "is_system": True},
    {"name": "PotatoVPN", "emoji_id": "5796403831646458962", "category": "VPN", "is_system": True},
    {"name": "PandaVPN", "emoji_id": "5796561774773801876", "category": "VPN", "is_system": True},
    {"name": "IPVanish", "emoji_id": "5796381996032725483", "category": "VPN", "is_system": True},
    {"name": "X-VPN", "emoji_id": "5794376731636798062", "category": "VPN", "is_system": True},

    # Payment Methods
    {"name": "bKash", "emoji_id": "6217678000977089090", "category": "Payment", "is_system": True},
    {"name": "Nagad", "emoji_id": "6217625168584380551", "category": "Payment", "is_system": True},
    {"name": "Rocket", "emoji_id": "4911601033496494993", "category": "Payment", "is_system": True},

    # Services & Platforms
    {"name": "ChatGPT", "emoji_id": "5453962468478962129", "category": "Services", "is_system": True},
    {"name": "Gemini", "emoji_id": "5262838511161076891", "category": "Services", "is_system": True},
    {"name": "YouTube", "emoji_id": "5796637619601283518", "category": "Services", "is_system": True},
    {"name": "Spotify", "emoji_id": "5796304385973686816", "category": "Services", "is_system": True},
    {"name": "TradingView", "emoji_id": "5796502474160346077", "category": "Services", "is_system": True},
    {"name": "Netflix", "emoji_id": "5796522630441867305", "category": "Services", "is_system": True},
    {"name": "ChatGPT (Icon)", "emoji_id": "5796185041717433060", "category": "Services", "is_system": True},
    {"name": "Canva", "emoji_id": "5796214303329620386", "category": "Services", "is_system": True},
    {"name": "Disney+", "emoji_id": "5794147784110117479", "category": "Services", "is_system": True},
    {"name": "Crunchyroll", "emoji_id": "5796297333637387376", "category": "Services", "is_system": True},
    {"name": "Telegram (Badge)", "emoji_id": "6264777724741556322", "category": "Services", "is_system": True},
    {"name": "CapCut", "emoji_id": "5244855659186383242", "category": "Services", "is_system": True},
    {"name": "YouTube (Alt)", "emoji_id": "5334769042886533147", "category": "Services", "is_system": True},
    {"name": "Newspaper", "emoji_id": "5336879280578138635", "category": "Services", "is_system": True},
    {"name": "Telegram (Plane)", "emoji_id": "5269215244810491516", "category": "Services", "is_system": True},

    # System UI Icons
    {"name": "Products / Shop", "emoji_id": "6084664543152183861", "category": "System", "is_system": True},
    {"name": "Shopping Cart", "emoji_id": "6102911544205515696", "category": "System", "is_system": True},
    {"name": "Add Balance", "emoji_id": "6233367447789899509", "category": "System", "is_system": True},
    {"name": "Refer & Earn", "emoji_id": "5379742233853451967", "category": "System", "is_system": True},
    {"name": "Money Coin", "emoji_id": "6251368935627692476", "category": "System", "is_system": True},
    {"name": "Orders / Gifts", "emoji_id": "6084747049473940188", "category": "System", "is_system": True},
    {"name": "User Profile", "emoji_id": "5208604387156448480", "category": "System", "is_system": True},
    {"name": "VIP Diamond", "emoji_id": "6084472820107057290", "category": "System", "is_system": True},
    {"name": "Crown", "emoji_id": "6102443543094105763", "category": "System", "is_system": True},
    {"name": "Lightning", "emoji_id": "6084566793991494246", "category": "System", "is_system": True},
    {"name": "Fire", "emoji_id": "6084435123179100660", "category": "System", "is_system": True},
    {"name": "Sparkles", "emoji_id": "5325547803936572038", "category": "System", "is_system": True},
    {"name": "Star", "emoji_id": "5337102391244263212", "category": "System", "is_system": True},
    {"name": "Loudspeaker Channel", "emoji_id": "6082236434930998087", "category": "System", "is_system": True},
    {"name": "Support Headphones", "emoji_id": "5438511323631609540", "category": "System", "is_system": True},
    {"name": "Rocket", "emoji_id": "5352597830089347330", "category": "System", "is_system": True},
    {"name": "Shield", "emoji_id": "5190447043545438788", "category": "System", "is_system": True},
    {"name": "Lock", "emoji_id": "6084535127197620168", "category": "System", "is_system": True},
    {"name": "Key", "emoji_id": "6105118564690172709", "category": "System", "is_system": True},
    {"name": "Stats Chart", "emoji_id": "5231200819986047254", "category": "System", "is_system": True},
    {"name": "Globe", "emoji_id": "5334590977837403844", "category": "System", "is_system": True},
    {"name": "Mail", "emoji_id": "5253742260054409879", "category": "System", "is_system": True},
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
            "category": "Custom",
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
        raise HTTPException(status_code=400, detail="Emoji ID must be a numeric Telegram custom emoji ID.")

    # Check if this ID is already in system emojis
    if any(s["emoji_id"] == cleaned_id for s in SYSTEM_EMOJIS):
        raise HTTPException(status_code=400, detail="This custom emoji ID already exists in built-in system emojis.")

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

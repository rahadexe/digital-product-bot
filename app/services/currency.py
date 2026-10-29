"""Presentation preferences for background financial notifications; amounts stay USD."""

from typing import Any


def preferred_currency(user: Any) -> str:
    currency = str((user or {}).get("currency") or "").strip().upper()
    if currency in {"USD", "BDT"}:
        return currency
    return "USD" if str((user or {}).get("language") or "").lower() == "en" else "BDT"


async def customer_pricing(db: Any, settings: Any, tg_user_id: int) -> dict[str, Any]:
    async with db.connect() as conn:
        user = await conn.fetchrow("SELECT currency, language FROM users WHERE tg_user_id=$1", tg_user_id)
    return {"currency": preferred_currency(user), "usd_rate": await settings.number("usd_rate")}

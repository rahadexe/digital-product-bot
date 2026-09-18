"""Store settings kept in the database. Each key is declared once with its default and validation."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.core.config import Settings
from app.core.money import money
from app.db import Database
from app.services.audit import record
from app.services.errors import InvalidInputError

logger = logging.getLogger("app.services.settings")

DEFAULT_GUIDE = (
    "📖 <b>How to Use This Bot:</b>\n\n"
    "1. <b>Deposit Funds:</b> Tap Deposit to top up your wallet.\n"
    "2. <b>Select Product:</b> Browse Shop and choose your subscription or key.\n"
    "3. <b>Instant Delivery:</b> Confirm purchase to receive credentials in chat.\n"
    "4. <b>Access Anytime:</b> All purchases are saved under Orders."
)


def _text(value: str) -> str:
    return value


def _flag(value: str) -> str:
    if value not in {"0", "1"}:
        raise ValueError("must be 0 or 1")
    return value


def _number(minimum: float, maximum: float) -> Callable[[str], str]:
    def parse(value: str) -> str:
        number = money(float(value))
        if not minimum <= number <= maximum:
            raise ValueError(f"must be between {minimum:g} and {maximum:g}")
        return f"{number:g}"

    return parse


def _telegram_id(value: str) -> str:
    value = value.strip()
    if not re.fullmatch(r"\d{0,20}", value):
        raise ValueError("must be a numeric Telegram ID")
    return value or "0"


def _telegram_ids(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    raw_ids = [part.strip() for part in re.split(r"[\s,;]+", value) if part.strip()]
    for pid in raw_ids:
        if not re.fullmatch(r"\d{5,20}", pid):
            raise ValueError(f"'{pid}' is not a valid Telegram user ID (must be numeric)")
    return ", ".join(raw_ids)


def _username(value: str) -> str:
    value = value.strip()
    if value and not re.fullmatch(r"@?[A-Za-z0-9_]{3,64}", value):
        raise ValueError("must be a Telegram username")
    return value


def _chat(value: str) -> str:
    value = value.strip()
    if value and not re.fullmatch(r"@[A-Za-z0-9_]{3,64}|-?\d{5,20}", value):
        raise ValueError("must be @channel or a numeric chat ID")
    return value


def _currency_code(value: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,10}", value):
        raise ValueError("must be a currency code such as USDT")
    return value


@dataclass(frozen=True)
class SettingSpec:
    default: str
    parse: Callable[[str], str] = _text
    max_length: int = 256
    # Secret values can be written but are never returned by the API.
    secret: bool = False


SPECS: dict[str, SettingSpec] = {
    "store_name": SettingSpec("PremiumOne", max_length=64),
    "store_tagline": SettingSpec("Premium digital subscriptions & accounts.", max_length=120),
    "store_description": SettingSpec("VPNs, Streaming & AI tools at your fingertips.", max_length=240),
    "currency": SettingSpec("BDT", _currency_code, 10),
    "currency_symbol": SettingSpec("৳", max_length=8),
    "validity_presets": SettingSpec("3 Days, 7 Days, 14 Days, 30 Days, 90 Days, 1 Year", max_length=2000),
    "custom_emojis": SettingSpec(
        '[{"name":"NordVPN","id":"5796345694969140339","icon":"🏔️"},{"name":"ExpressVPN","id":"5796153709931009517","icon":"🔴"},{"name":"Surfshark","id":"5796592771552777710","icon":"🦈"},{"name":"Proton VPN","id":"5794298344188678751","icon":"🛡️"},{"name":"CyberGhost","id":"5796309230696797985","icon":"👻"},{"name":"HMA VPN","id":"5796595022115639741","icon":"🕶️"},{"name":"Bitdefender","id":"5793973558761756143","icon":"🛡️"},{"name":"IPVanish","id":"5796567478490371776","icon":"🔒"},{"name":"Windscribe","id":"5794045349140108622","icon":"🟢"},{"name":"X-VPN","id":"5794376731636798062","icon":"⬜"},{"name":"PotatoVPN","id":"5796403831646458962","icon":"🟡"},{"name":"PandaVPN","id":"5796561774773801876","icon":"🐼"},{"name":"PureVPN","id":"5794156713347126602","icon":"🟣"},{"name":"VyprVPN","id":"5796381996032725483","icon":"🦎"},{"name":"Turbo VPN","id":"5796633857209931262","icon":"🟠"},{"name":"AdGuard","id":"5796674118233363546","icon":"✈️"},{"name":"ChatGPT","id":"6084700423308975252","icon":"🤖"},{"name":"Claude","id":"5278628322769654561","icon":"🧠"},{"name":"Midjourney","id":"5190751148704833975","icon":"🎨"},{"name":"GitHub","id":"6251457360414382759","icon":"💻"},{"name":"Canva","id":"5352552689983067014","icon":"✨"},{"name":"Netflix","id":"5960740614810112719","icon":"🍿"},{"name":"Spotify","id":"5463107823946717464","icon":"🎵"},{"name":"YouTube","id":"5264919878082509254","icon":"📺"},{"name":"Telegram","id":"6082362698379565136","icon":"⭐"}]',
        max_length=15000,
    ),
    "support_username": SettingSpec("", _username, 65),
    "notice_banner": SettingSpec("", max_length=1000),
    "welcome_text": SettingSpec("", max_length=3500),
    "guide_text": SettingSpec(DEFAULT_GUIDE, max_length=3500),
    "referral_enabled": SettingSpec("1", _flag, 1),
    "referral_reward_amount": SettingSpec("3.0", _number(0, 100), 16),
    "referral_bonus_percent": SettingSpec("0", _number(0, 100), 16),
    "force_join_enabled": SettingSpec("0", _flag, 1),
    "store_paused": SettingSpec("0", _flag, 1),
    "maintenance_message": SettingSpec("Store maintenance is in progress. Please try again soon.", max_length=240),
    "max_deposit_limit": SettingSpec("50000", _number(1, 1_000_000_000), 16),
    "admin_tg_id": SettingSpec("0", _telegram_id, 20),
    "admin_tg_ids": SettingSpec("", _telegram_ids, 1000),
    "notify_admin_orders": SettingSpec("1", _flag, 1),
    "notify_admin_deposits": SettingSpec("1", _flag, 1),
    "notify_admin_payments": SettingSpec("1", _flag, 1),
    "notify_admin_restock": SettingSpec("1", _flag, 1),
    "notify_admin_new_user": SettingSpec("0", _flag, 1),
    "announcement_channel": SettingSpec("", _chat, 65),
    "auto_restock_alerts": SettingSpec("1", _flag, 1),
    "auto_price_drop_alerts": SettingSpec("1", _flag, 1),
    "supplier_api_url": SettingSpec(""),
    "supplier_api_key": SettingSpec("", secret=True),
    # ZiniPay instant payments: credited automatically after ZiniPay confirms each payment.
    "zinipay_enabled": SettingSpec("0", _flag, 1),
    "zinipay_api_key": SettingSpec("", secret=True),
    "zinipay_brand_url": SettingSpec("", max_length=256),
    "zinipay_rate": SettingSpec("1.0", _number(0.0001, 1_000_000), 16),
    "zinipay_min_deposit": SettingSpec("1", _number(0.01, 1_000_000_000), 16),
    "zinipay_label": SettingSpec("bKash / Nagad · Instant", max_length=40),
    # USDT deposits confirmed against the shop's own Binance account with a read-only API key.
    "binance_enabled": SettingSpec("0", _flag, 1),
    "binance_api_key": SettingSpec("", secret=True),
    "binance_api_secret": SettingSpec("", secret=True),
    "binance_coin": SettingSpec("USDT", _currency_code, 10),
    "binance_pay_id": SettingSpec("12345678", max_length=64),
    "binance_pay_rate": SettingSpec("125", _number(0.0001, 1_000_000), 16),
    "binance_pay_min": SettingSpec("100", _number(0.01, 1_000_000_000), 16),
    "binance_pay_instructions": SettingSpec("", max_length=1000),
}


class SettingsService:
    CACHE_SECONDS = 30.0

    def __init__(self, db: Database, config: Settings):
        self.db = db
        self.config = config
        self._cache: tuple[float, dict[str, str]] | None = None

    def _validate(self, key: str, raw: str) -> str:
        spec = SPECS[key]
        if len(raw) > spec.max_length:
            raise ValueError(f"is longer than {spec.max_length} characters")
        value = spec.parse(raw)
        if key == "supplier_api_url" and value:
            from app.services.supplier import validate_supplier_url

            value = validate_supplier_url(value, self.config)
        return value

    async def values(self) -> dict[str, str]:
        """Every declared setting: the stored value when it is valid, otherwise the default."""
        now = time.monotonic()
        if self._cache and now - self._cache[0] < self.CACHE_SECONDS:
            return dict(self._cache[1])
        async with self.db.connect() as conn:
            stored = {row["key"]: row["value"] for row in await conn.fetch("SELECT key, value FROM bot_settings")}
        values = {}
        for key, spec in SPECS.items():
            raw = stored.get(key)
            try:
                values[key] = spec.default if raw is None else self._validate(key, raw)
            except ValueError:
                logger.warning("Stored setting %s is invalid; using its default.", key)
                values[key] = spec.default
        self._cache = (now, values)
        return dict(values)

    async def public(self) -> dict[str, str]:
        return {key: value for key, value in (await self.values()).items() if not SPECS[key].secret}

    async def get(self, key: str) -> str:
        return (await self.values())[key]

    async def flag(self, key: str) -> bool:
        return await self.get(key) == "1"

    async def number(self, key: str) -> float:
        return float(await self.get(key))

    async def paused_message(self) -> str:
        """What customers are told while the store is paused, or an empty string when it is open."""
        values = await self.values()
        return values["maintenance_message"] if values["store_paused"] == "1" else ""

    async def admin_chat_ids(self) -> list[int]:
        values = await self.values()
        raw = values.get("admin_tg_ids", "").strip()
        ids: list[int] = []
        if raw:
            for part in re.split(r"[\s,;]+", raw):
                if part.isdigit():
                    ids.append(int(part))
        if not ids:
            single = int(values.get("admin_tg_id", 0)) or self.config.admin_tg_id
            if single:
                ids.append(single)
        return list(dict.fromkeys(ids))

    async def admin_chat_id(self) -> int:
        ids = await self.admin_chat_ids()
        return ids[0] if ids else (self.config.admin_tg_id or 0)

    async def supplier_credentials(self) -> tuple[str, str]:
        values = await self.values()
        return (
            values["supplier_api_url"] or self.config.supplier_api_url,
            values["supplier_api_key"] or self.config.supplier_api_key,
        )

    async def update(self, changes: dict[str, str]) -> list[str]:
        """Validate every change first, then write them together. Returns the keys that changed."""
        unknown = sorted(set(changes) - SPECS.keys())
        if unknown:
            raise InvalidInputError(f"Unknown setting: {', '.join(unknown)}.")
        cleaned = {}
        for key, raw in changes.items():
            try:
                cleaned[key] = self._validate(key, str(raw))
            except ValueError as exc:
                raise InvalidInputError(f"Setting {key} {exc}.") from None

        self._cache = None
        current = await self.values()
        changed = [key for key, value in cleaned.items() if current[key] != value]
        if changed:
            async with self.db.transaction() as conn:
                await conn.executemany(
                    "INSERT INTO bot_settings (key, value) VALUES ($1, $2) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                    [(key, cleaned[key]) for key in changed],
                )
                await record(conn, "settings_updated", "Changed: " + ", ".join(sorted(changed)))
            self._cache = None
        return changed

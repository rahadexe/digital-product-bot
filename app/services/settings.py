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
        # Positive only. A negative id is a group or a channel, and these ids are
        # who the order and deposit alerts are sent to, which name the customer,
        # their Telegram id, what they bought and what they paid. Sending that to
        # a channel publishes it to everyone subscribed. Channels belong in
        # announcement_channel, which carries no customer details.
        if not re.fullmatch(r"\d{5,20}", pid):
            raise ValueError(
                f"'{pid}' is not a Telegram user ID. Groups and channels cannot be administrators, "
                f"because admin alerts contain customer details"
            )
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


def _chats(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    parts = [p.strip() for p in re.split(r"[\s,;]+", value) if p.strip()]
    for p in parts:
        if not re.fullmatch(r"@[A-Za-z0-9_]{3,64}|-?\d{5,20}", p):
            raise ValueError(f"'{p}' must be @channel or numeric chat ID")
    return ", ".join(parts)


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
    "currency": SettingSpec("BDT", _currency_code, 10),
    "currency_symbol": SettingSpec("৳", max_length=8),
    "usd_rate": SettingSpec("125", _number(0.0001, 1_000_000), 16),
    "validity_presets": SettingSpec("", max_length=2000),
    "support_username": SettingSpec("@rahadhasanrafi", _username, 65),
    "referral_enabled": SettingSpec("1", _flag, 1),
    "referral_reward_amount": SettingSpec("3.0", _number(0, 100), 16),
    "force_join_enabled": SettingSpec("0", _flag, 1),
    "store_paused": SettingSpec("0", _flag, 1),
    "maintenance_message": SettingSpec("Store maintenance is in progress. Please try again soon.", max_length=240),
    "max_deposit_limit": SettingSpec("50000", _number(1, 1_000_000_000), 16),
    "admin_tg_id": SettingSpec("0", _telegram_id, 20),
    "admin_tg_ids": SettingSpec("", _telegram_ids, 1000),
    "notify_admin_orders": SettingSpec("0", _flag, 1),
    "notify_admin_deposits": SettingSpec("1", _flag, 1),
    "notify_admin_payments": SettingSpec("0", _flag, 1),
    "notify_admin_restock": SettingSpec("1", _flag, 1),
    "notify_admin_low_stock": SettingSpec("1", _flag, 1),
    "low_stock_threshold": SettingSpec("3", _number(1, 100), 4),
    "notify_admin_price_change": SettingSpec("1", _flag, 1),
    "notify_admin_new_user": SettingSpec("0", _flag, 1),
    "notify_user_referral": SettingSpec("1", _flag, 1),
    "announcement_channel": SettingSpec("", _chats, 500),
    "auto_restock_alerts": SettingSpec("1", _flag, 1),
    "auto_price_drop_alerts": SettingSpec("1", _flag, 1),
    # ZiniPay instant payments: credited automatically after ZiniPay confirms each payment.
    "zinipay_enabled": SettingSpec("0", _flag, 1),
    "zinipay_web_gateway_enabled": SettingSpec("0", _flag, 1),
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
    "binance_pay_name": SettingSpec("", max_length=100),
    # Upstream Digital Mart Reseller provider settings
    "upstream_reseller_url": SettingSpec("https://dmb.bmdigital.bd/api/v1/reseller", max_length=256),
    "upstream_reseller_key": SettingSpec("", secret=True),
    "upstream_markup_percent": SettingSpec("15.0", _number(0, 500), 16),
    "upstream_auto_sync": SettingSpec("1", _flag, 1),
    "upstream_low_balance_alert": SettingSpec("50.0", _number(0, 100000), 16),
    "upstream_low_balance_notify": SettingSpec("1", _flag, 1),
    # Upstream Safwan Tiger Shop provider settings
    "safwan_tiger_url": SettingSpec("https://safwantigershopbot-production.up.railway.app/api", max_length=256),
    "safwan_tiger_key": SettingSpec("", secret=True),
    "safwan_tiger_markup_percent": SettingSpec("15.0", _number(0, 500), 16),
    "safwan_tiger_auto_sync": SettingSpec("0", _flag, 1),
    "safwan_tiger_low_balance_alert": SettingSpec("5.0", _number(0, 100000), 16),
    "safwan_tiger_low_balance_notify": SettingSpec("1", _flag, 1),
    # Resilient supplier fallback: queue order as waiting rather than rolling back when supplier is out of balance
    "supplier_fallback_to_waiting": SettingSpec("1", _flag, 1),
    "binance_pay_rate": SettingSpec("125", _number(0.0001, 1_000_000), 16),
    "binance_pay_min": SettingSpec("1", _number(0.01, 1_000_000_000), 16),
    "binance_pay_instructions": SettingSpec("", max_length=1000),
}


def mask_secret(value: str) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    if len(s) <= 8:
        return "****"
    return f"{s[:4]}{'*' * 16}{s[-4:]}"


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
        fixed = {'currency': 'BDT', 'currency_symbol': '৳', 'zinipay_rate': '1'}
        if key in fixed:
            if key == 'zinipay_rate':
                if float(value) != 1:
                    raise ValueError('must remain 1 for the BDT wallet')
            elif value != fixed[key]:
                raise ValueError(f'must remain {fixed[key]} for the BDT wallet')
            return fixed[key]
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
                if key == "admin_tg_ids":
                    # Falling back to "" here would mean nobody receives an alert,
                    # silently, because one entry in the list was wrong. Keep the
                    # entries that are valid and drop only the offending ones.
                    salvaged = [part for part in re.split(r"[\s,;]+", raw or "")
                                if part.isdigit() and int(part) > 0]
                    if salvaged:
                        logger.warning("Keeping %d valid administrator id(s) from %s.", len(salvaged), key)
                        values[key] = ", ".join(salvaged)
        self._cache = (now, values)
        try:
            from app.bot.formatting import configure_pricing
            usd_rate = float(values.get("usd_rate", "125"))
            configure_pricing(usd_rate=usd_rate)
        except Exception:
            pass
        return dict(values)

    async def public(self) -> dict[str, str]:
        values = await self.values()
        res = {}
        for key, spec in SPECS.items():
            if spec.secret:
                raw = values.get(key, "").strip()
                res[key] = mask_secret(raw) if raw else ""
            else:
                res[key] = values.get(key, "")
        return res

    async def get(self, key: str) -> str:
        vals = await self.values()
        if key not in vals:
            return "0" if key == "show_usd_price" else ""
        return vals[key]

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
                # The validator refuses a group or channel id, and so does this:
                # a value stored before that rule existed must not start
                # delivering customer details to a channel.
                if part.isdigit() and int(part) > 0:
                    ids.append(int(part))
        if not ids:
            single = int(values.get("admin_tg_id", 0)) or self.config.admin_tg_id
            if single:
                ids.append(single)
        return list(dict.fromkeys(ids))

    async def admin_chat_id(self) -> int:
        ids = await self.admin_chat_ids()
        return ids[0] if ids else (self.config.admin_tg_id or 0)

    async def update(self, changes: dict[str, str]) -> list[str]:
        """Validate every change first, then write them together. Returns the keys that changed."""
        # Ignore masked secret values so placeholders like 81a8****************4b27 are never saved to database
        changes = {
            k: v for k, v in changes.items()
            if not (k in SPECS and SPECS[k].secret and "*" in str(v))
        }
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

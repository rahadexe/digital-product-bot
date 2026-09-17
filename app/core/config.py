from __future__ import annotations

import re
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Process configuration from the environment. Store behaviour is kept in the database."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal['development', 'testing', 'production'] = "development"
    host: str = "127.0.0.1"
    port: int = 8000
    database_url: str = ""
    db_pool_size: int = Field(default=10, ge=1, le=100)
    # Prepared statements save one database round trip per query. Set 0 only for a
    # connection pooler that does not support prepared statements (Neon's pooler does).
    db_statement_cache_size: int = Field(default=100, ge=0)
    redis_url: str = ""
    auto_migrate: bool = True

    bot_token: str = ""
    admin_tg_id: int = 0
    webapp_url: str = ""
    webhook_base_url: str = ""
    webhook_secret: str = ""

    admin_password: str = ""
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    cookie_secure: bool = False
    allowed_hosts: str = 'localhost,127.0.0.1,[::1],test'
    allowed_origins: str = ''
    trusted_proxy_ips: str = '127.0.0.1'

    supplier_api_url: str = "https://safwantigershopbot-production.up.railway.app/api"
    supplier_api_key: str = ""
    supplier_allowed_hosts: str = "safwantigershopbot-production.up.railway.app"
    # Optional: the ZiniPay brand API key; the admin console setting takes precedence when set.
    zinipay_api_key: str = ""
    # Optional: read-only Binance API credentials for confirming USDT deposits; the console settings win.
    binance_api_key: str = ""
    binance_api_secret: str = ""

    @model_validator(mode="after")
    def validate_security(self):
        if self.admin_password == 'admin123456':
            raise ValueError('Replace the default ADMIN_PASSWORD in .env before starting the store.')
        weak_secret = len(self.secret_key) < 32 or "change_me" in self.secret_key
        # The store serves the Mini App at /app/ and the operator console at the root, so a WEBAPP_URL
        # that names only the domain would open the console inside Telegram.
        if self.webapp_url:
            self.webapp_url = self.mini_app_url(self.webapp_url)
        if self.webhook_base_url:
            self.webhook_base_url = self.webhook_base_url.rstrip("/")
        if self.telegram_enabled:
            if not self.webhook_base_url or not self.webhook_base_url.startswith("https://"):
                raise ValueError("Set WEBHOOK_BASE_URL to the public https address Telegram should send updates to.")
            if not self.webhook_secret:
                if self.app_env == "production":
                    raise ValueError("Production requires WEBHOOK_SECRET.")
                self.webhook_secret = secrets.token_urlsafe(32)
            elif not re.match(r"^[A-Za-z0-9_-]{32,256}$", self.webhook_secret):
                raise ValueError(
                    "WEBHOOK_SECRET must match ^[A-Za-z0-9_-]{32,256}$."
                )
        if self.app_env == "production":
            if weak_secret or len(self.admin_password) < 12:
                raise ValueError("Production requires a strong ADMIN_PASSWORD and SECRET_KEY.")
            if not self.database_url:
                raise ValueError("Production requires DATABASE_URL.")
            if self.webapp_url and not self.webapp_url.startswith("https://"):
                raise ValueError("WEBAPP_URL must be an https:// address; Telegram opens Mini Apps only over HTTPS.")
            self.cookie_secure = True
        elif weak_secret:
            self.secret_key = secrets.token_urlsafe(48)
        return self

    @property
    def webhook_url(self) -> str:
        return f"{self.webhook_base_url}/telegram/webhook"

    @staticmethod
    def mini_app_url(url: str) -> str:
        """The same address pointed at /app/, whatever path it was given."""
        parts = urlsplit(url.strip())
        if not parts.scheme or not parts.netloc:
            return url.strip()
        path = parts.path if parts.path.rstrip("/").endswith("/app") else "/app"
        return urlunsplit((parts.scheme, parts.netloc, path.rstrip("/") + "/", "", ""))

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.bot_token) and self.bot_token != "your_bot_token_here"

    @staticmethod
    def split(value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

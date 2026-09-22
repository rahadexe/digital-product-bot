"""Application services.

HTTP routes and Telegram handlers call these services; only services read or
write the database. ``build_services`` wires one instance of each per process.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.core.config import Settings
from app.db import Database
from app.services.admin_access import AdminAccessService
from app.services.announcements import AnnouncementService
from app.services.audit import AuditService
from app.services.binance import BinanceDepositService
from app.services.catalog import CatalogService
from app.services.dashboard import DashboardService
from app.services.delivery import DeliveryService
from app.services.deposits import DepositService
from app.services.gate import GateService
from app.services.inventory import InventoryService
from app.services.notifications import Notifier
from app.services.payments import PaymentService
from app.services.purchases import PurchaseService
from app.services.rate_limits import RateLimits
from app.services.reseller import ResellerService
from app.services.settings import SettingsService
from app.services.update_channels import UpdateChannelService
from app.services.users import UserService
from app.services.zinipay import ZiniPayVerificationService


@dataclass
class RuntimeStatus:
    """What this process is running, for health checks."""

    bot: str = "disabled"  # disabled | starting | webhook
    dispatcher: Any = None
    tasks: list[asyncio.Task] = field(default_factory=list)
    update_tasks: set[asyncio.Task] = field(default_factory=set)
    inbox_wake: asyncio.Event = field(default_factory=asyncio.Event)

    def components_alive(self) -> bool:
        return all(not task.done() for task in self.tasks)


@dataclass
class Services:
    config: Settings
    db: Database
    settings: SettingsService
    notifier: Notifier
    audit: AuditService
    users: UserService
    catalog: CatalogService
    inventory: InventoryService
    delivery: DeliveryService
    purchases: PurchaseService
    deposits: DepositService
    payments: PaymentService
    binance: BinanceDepositService
    zinipay: ZiniPayVerificationService
    gate: GateService
    update_channels: UpdateChannelService
    announcements: AnnouncementService
    dashboard: DashboardService
    admin_access: AdminAccessService
    reseller: ResellerService
    rate_limits: RateLimits
    runtime: RuntimeStatus = field(default_factory=RuntimeStatus)

    async def close(self) -> None:
        await self.notifier.drain()
        await asyncio.gather(self.payments.http.aclose(), self.binance.http.aclose(), self.zinipay.http.aclose())
        if self.notifier.bot is not None:
            await self.notifier.bot.session.close()
        await self.db.close()


def build_services(
    config: Settings,
    *,
    db: Database | None = None,
    bot: Bot | None = None,
    use_telegram: bool = True,
) -> Services:
    db = db or Database(
        config.database_url,
        max_size=config.db_pool_size,
        statement_cache_size=config.db_statement_cache_size,
    )
    if bot is None and use_telegram and config.telegram_enabled:
        bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    settings = SettingsService(db, config)
    notifier = Notifier(bot, settings)
    catalog = CatalogService(db)
    delivery = DeliveryService(db)
    deposits = DepositService(db, settings, notifier)
    users = UserService(db, settings, notifier)
    reseller = ResellerService(db, settings, catalog, users)

    limits = RateLimits(db)
    purchases = PurchaseService(db, settings, delivery, notifier)
    # Stock warnings need a quiet period; the limiter is the only thing that remembers
    # across restarts and replicas.
    purchases.rate_limits = limits

    return Services(
        config=config,
        db=db,
        settings=settings,
        notifier=notifier,
        audit=AuditService(db),
        users=users,
        catalog=catalog,
        inventory=InventoryService(db),
        delivery=delivery,
        purchases=purchases,
        deposits=deposits,
        payments=PaymentService(db, settings, notifier, config),
        binance=BinanceDepositService(db, settings, deposits, notifier, config),
        zinipay=ZiniPayVerificationService(db, settings, deposits, notifier, config),
        gate=GateService(db, settings, notifier),
        update_channels=UpdateChannelService(db),
        announcements=AnnouncementService(settings, catalog, notifier),
        dashboard=DashboardService(db),
        admin_access=AdminAccessService(db),
        reseller=reseller,
        rate_limits=limits,
    )

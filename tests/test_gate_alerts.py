"""Admin alerts must not depend on the host machine's uptime."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.gate import GateService


@pytest.mark.asyncio
@pytest.mark.parametrize("uptime", [0.0, 5.0, 899.0])
async def test_first_channel_alert_is_sent_on_fresh_host(uptime):
    notifier = SimpleNamespace(send_admin=AsyncMock())
    gate = GateService(None, None, notifier)
    channel = {"channel_username": "@test", "title": "Test", "error_reason": "Unavailable"}
    with patch("app.services.gate.time", SimpleNamespace(monotonic=lambda: uptime)):
        await gate.notify_admin_channel_issue([channel])
    notifier.send_admin.assert_awaited_once()


@pytest.mark.asyncio
async def test_channel_alert_cooldown_starts_after_first_alert():
    notifier = SimpleNamespace(send_admin=AsyncMock())
    gate = GateService(None, None, notifier)
    channel = {"channel_username": "@test"}
    clock = [0.0]
    with patch("app.services.gate.time", SimpleNamespace(monotonic=lambda: clock[0])):
        await gate.notify_admin_channel_issue([channel])
        clock[0] = 899.0
        await gate.notify_admin_channel_issue([channel])
        assert notifier.send_admin.await_count == 1
        clock[0] = 900.0
        await gate.notify_admin_channel_issue([channel])
    assert notifier.send_admin.await_count == 2


@pytest.mark.asyncio
async def test_channel_alert_cooldown_does_not_hide_another_channel():
    notifier = SimpleNamespace(send_admin=AsyncMock())
    gate = GateService(None, None, notifier)
    with patch("app.services.gate.time", SimpleNamespace(monotonic=lambda: 5.0)):
        await gate.notify_admin_channel_issue([{"channel_username": "@first"}])
        await gate.notify_admin_channel_issue([{"channel_username": "@second"}])
    assert notifier.send_admin.await_count == 2

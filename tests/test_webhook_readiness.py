import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from aiogram.types import CallbackQuery, Chat, Message, User
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import GetChatMember

from app.bot.handlers.start import handle_gate_verify
from app.bot.middlewares import StoreAccess
from app.services.gate import GateService
from app.runtime import run_webhook


def gate_service(member=True):
    notifier = SimpleNamespace(is_member=AsyncMock(return_value=member))
    gate = GateService(None, SimpleNamespace(flag=AsyncMock(return_value=True)), notifier)
    gate.channels = AsyncMock(return_value=[{'chat_id': '-100123', 'title': 'Required'}])
    return gate


@pytest.mark.asyncio
@pytest.mark.parametrize('member', [True, False])
async def test_concurrent_checks_and_repeated_taps_share_one_request(member):
    gate = gate_service(member)
    results = await asyncio.gather(*(gate.check(123) for _ in range(50)))
    assert all(result[0] is member for result in results)
    for _ in range(20):
        assert (await gate.check(123))[0] is member
    gate.notifier.is_member.assert_awaited_once()
    assert not gate._checks


@pytest.mark.asyncio
async def test_join_or_leave_invalidates_both_caches():
    gate = gate_service(False)
    assert not (await gate.check(123))[0]
    gate.notifier.is_member.return_value = True
    gate.forget(123)
    assert (await gate.check(123))[0]
    gate.notifier.is_member.return_value = False
    gate.forget(123)
    assert not (await gate.check(123))[0]
    assert gate.notifier.is_member.await_count == 3


@pytest.mark.asyncio
async def test_invalidated_inflight_result_cannot_restore_cached_access():
    gate = gate_service()
    started, finish = asyncio.Event(), asyncio.Event()
    async def member(*args):
        started.set()
        await finish.wait()
        return True
    gate.notifier.is_member.side_effect = member
    check = asyncio.create_task(gate.check(123))
    await started.wait()
    gate.forget(123)
    finish.set()
    await check
    assert 123 not in gate._verified


@pytest.mark.asyncio
async def test_cancelling_waiter_does_not_leave_inflight_entry():
    gate = gate_service()
    started, finish = asyncio.Event(), asyncio.Event()
    async def member(*args):
        started.set()
        await finish.wait()
        return True
    gate.notifier.is_member.side_effect = member
    check = asyncio.create_task(gate.check(123))
    await started.wait()
    task = gate._checks[123]
    check.cancel()
    with pytest.raises(asyncio.CancelledError):
        await check
    finish.set()
    await task
    await asyncio.sleep(0)
    assert not gate._checks


@pytest.mark.asyncio
async def test_slow_telegram_check_is_bounded_and_not_verified():
    gate = gate_service()
    gate.notifier.is_member.side_effect = lambda *args: None
    async def slow(*args):
        await asyncio.sleep(60)
    gate.notifier.is_member.side_effect = slow
    with patch('app.services.gate.MEMBERSHIP_TIMEOUT_SECONDS', 0.02):
        passed, missing = await asyncio.wait_for(gate.check(123), timeout=1)
    assert not passed and missing[0]['verification_unavailable']
    assert 123 not in gate._verified


@pytest.mark.asyncio
async def test_rate_limit_cools_down_channel_for_other_customers():
    gate = gate_service()
    gate.notifier.is_member.side_effect = TelegramRetryAfter(
        method=GetChatMember(chat_id=-100123, user_id=123), message='Retry later', retry_after=30)
    assert not (await gate.check(123))[0]
    assert not (await gate.check(456))[0]
    gate.notifier.is_member.assert_awaited_once()
    assert not gate._verified


def event(text='Account'):
    return Message(message_id=1, date=datetime.now(timezone.utc),
                   chat=Chat(id=123, type='private'),
                   from_user=User(id=123, is_bot=False, first_name='Test'), text=text)


def services_for_access(missing=None):
    # Close scheduled notification coroutines without contacting Telegram.
    return SimpleNamespace(
        settings=SimpleNamespace(admin_chat_ids=AsyncMock(return_value=[]),
                                 flag=AsyncMock(return_value=True), get=AsyncMock(return_value='Store')),
        users=SimpleNamespace(get=AsyncMock(return_value={'is_banned': 0}), process_referral_reward=AsyncMock()),
        notifier=SimpleNamespace(in_background=Mock(side_effect=lambda coro: coro.close())),
        gate=SimpleNamespace(check=AsyncMock(return_value=(False, missing or [{'title': 'Required'}])),
                             grant_access=Mock(), notify_admin_channel_issue=AsyncMock()),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('opening', ['/start', '/menu', 'gate_verify'])
async def test_opening_gate_never_caches_an_unverified_pass(opening):
    middleware, services, handler = StoreAccess(), services_for_access(), AsyncMock()
    first = event(opening)
    if opening == 'gate_verify':
        first = CallbackQuery(id='q', from_user=first.from_user, chat_instance='test', message=first, data=opening)
    await middleware(handler, first, {'services': services})
    handler.reset_mock()
    with patch.object(Message, 'answer', new_callable=AsyncMock):
        await middleware(handler, event(), {'services': services})
    handler.assert_not_awaited()
    services.gate.check.assert_awaited_once()


@pytest.mark.asyncio
async def test_verification_error_never_unlocks_or_awards_referral():
    missing = [{'title': 'Required', 'verification_unavailable': True}]
    services = services_for_access(missing)
    message = event()
    query = CallbackQuery(id='q', from_user=message.from_user, chat_instance='test', message=message, data='gate_verify')
    with patch.object(CallbackQuery, 'answer', new_callable=AsyncMock) as answer:
        await handle_gate_verify(query, SimpleNamespace(clear=AsyncMock()), services)
        assert answer.await_args.kwargs['show_alert']
    services.gate.grant_access.assert_not_called()
    services.users.process_referral_reward.assert_not_awaited()
    handler = AsyncMock()
    with patch.object(Message, 'answer', new_callable=AsyncMock):
        await StoreAccess()(handler, message, {'services': services})
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_repeated_blocked_actions_do_not_flood_join_prompts():
    middleware, services, handler = StoreAccess(), services_for_access(), AsyncMock()
    with patch.object(Message, 'answer', new_callable=AsyncMock) as answer:
        for _ in range(20):
            await middleware(handler, event(), {'services': services})
        answer.assert_awaited_once()
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_webhook_retries_transient_bot_configuration_failure():
    bot = SimpleNamespace(set_webhook=AsyncMock())
    storage = SimpleNamespace(close=AsyncMock())
    dispatcher = SimpleNamespace(resolve_used_update_types=lambda: ['message', 'callback_query', 'chat_member'], storage=storage)
    services = SimpleNamespace(
        notifier=SimpleNamespace(bot=bot, configure_bot=AsyncMock(side_effect=[OSError('temporary'), None])),
        runtime=SimpleNamespace(dispatcher=dispatcher, update_tasks=set(), bot='starting'),
        config=SimpleNamespace(webapp_url='', webhook_url='https://example.test/telegram/webhook', webhook_secret='s' * 40),
    )
    with patch('app.runtime.asyncio.sleep', AsyncMock(side_effect=[None, asyncio.CancelledError])):
        with pytest.raises(asyncio.CancelledError):
            await run_webhook(services)
    assert services.notifier.configure_bot.await_count == 2
    bot.set_webhook.assert_awaited_once()
    assert bot.set_webhook.await_args.kwargs['drop_pending_updates'] is False
    assert 'chat_member' in bot.set_webhook.await_args.kwargs['allowed_updates']
    storage.close.assert_awaited_once()


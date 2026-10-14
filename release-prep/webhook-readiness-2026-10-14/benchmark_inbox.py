"""Disposable local database only; no Telegram calls or application environment."""
import asyncio
import json
import time
import uuid
from collections import Counter
from types import SimpleNamespace

import asyncpg

from app.db import Database
from app.db.migrations import migrate
from app.workers.telegram import TelegramInboxWorker


async def main():
    dsn = 'postgresql://postgres@127.0.0.1:55432/audit_utf8'
    schema = 'test_inbox_' + uuid.uuid4().hex
    db = Database(dsn, schema=schema, max_size=10)
    try:
        await migrate(db)
        rows = []
        for update_id in range(1, 201):
            user = (update_id - 1) % 20 + 1
            payload = {'update_id': update_id, 'message': {'message_id': update_id, 'date': 1700000000,
                       'chat': {'id': user, 'type': 'private'},
                       'from': {'id': user, 'is_bot': False, 'first_name': 'Test'}, 'text': '/start'}}
            rows.append((update_id, user, json.dumps(payload)))
        async with db.connect() as conn:
            await conn.executemany('INSERT INTO telegram_inbox(update_id,customer_id,payload) VALUES($1,$2,$3::jsonb)', rows)
        active, seen, last = Counter(), [], {}
        peak = 0
        async def feed_update(bot, update):
            nonlocal peak
            user = update.message.from_user.id
            active[user] += 1
            assert active[user] == 1, 'Overlapping dispatch for same customer'
            assert update.update_id > last.get(user, 0), 'Customer updates dispatched out of order'
            peak = max(peak, sum(active.values()))
            await asyncio.sleep(0.005)
            seen.append(update.update_id)
            last[user] = update.update_id
            active[user] -= 1
        services = SimpleNamespace(db=db, notifier=SimpleNamespace(bot=None),
                                   runtime=SimpleNamespace(dispatcher=SimpleNamespace(feed_update=feed_update)))
        worker = TelegramInboxWorker(services)
        async def consume():
            while await worker.step():
                pass
        start = time.perf_counter()
        async with asyncio.timeout(60):
            await asyncio.gather(*(consume() for _ in range(4)))
        duration = time.perf_counter() - start
        async with db.connect() as conn:
            done = await conn.fetchval("SELECT count(*) FROM telegram_inbox WHERE status='done'")
        assert done == 200 and len(seen) == len(set(seen)) == 200
        print(json.dumps({'updates': done, 'customers': 20, 'workers': 4,
                          'seconds': round(duration, 3), 'updates_per_second': round(done / duration, 2),
                          'peak_concurrent_dispatch': peak, 'duplicates': 0,
                          'per_customer_order_preserved': True,
                          'scope': 'Local synthetic inbox only; excludes real Telegram, providers and webhook HTTP ingress'}))
    finally:
        await db.close()
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            await conn.close()


asyncio.run(main())

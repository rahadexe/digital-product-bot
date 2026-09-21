"""Local service benchmark: TEST_DATABASE_URL must point to disposable local PostgreSQL.

Run: python tests/benchmark_purchase.py (with the repository on PYTHONPATH).
This measures transactions, not real Telegram/provider or production network latency.
"""

import asyncio
import json
import os
import statistics
import time
import uuid
from urllib.parse import urlsplit

import asyncpg

from app.core.config import Settings
from app.db import Database
from app.db.migrations import migrate
from app.services import build_services


async def main():
    dsn = os.environ['TEST_DATABASE_URL']
    if urlsplit(dsn).hostname not in ('localhost', '127.0.0.1', '::1'):
        raise RuntimeError('Benchmark refuses non-local databases')
    schema = 'benchmark_' + uuid.uuid4().hex
    db = Database(dsn, schema=schema, max_size=12)
    config = Settings(_env_file=None,app_env='testing',database_url=dsn,bot_token='',secret_key='b'*48)
    services = build_services(config,db=db,use_telegram=False)
    try:
        await migrate(db)
        product = await services.catalog.create_product(None,'Benchmark',price=10)
        await services.inventory.add_stock(product,[f'dummy-{i}' for i in range(100)])
        async with db.connect() as conn:
            await conn.executemany('INSERT INTO users(tg_user_id,balance) VALUES($1,100)',[(i,) for i in range(1000,1100)])
        await services.settings.values()
        gate = asyncio.Semaphore(10)
        async def purchase(i):
            async with gate:
                started = time.perf_counter()
                result = await services.purchases.purchase(i,product,request_id=f'load-{i}')
                assert result[0], result[1]
                return (time.perf_counter()-started)*1000
        started = time.perf_counter()
        latencies = sorted(await asyncio.gather(*(purchase(i) for i in range(1000,1100))))
        elapsed = time.perf_counter()-started
        async with db.connect() as conn:
            assert await conn.fetchval('SELECT count(*) FROM orders') == 100
            assert await conn.fetchval('SELECT sum(balance) FROM users') == 9000
            assert await conn.fetchval('SELECT sum(uses) FROM inventory_items') == 100
        print(json.dumps({'orders':100,'concurrency':10,'seconds':round(elapsed,3),
                          'orders_per_second':round(100/elapsed,2),'p50_ms':round(statistics.median(latencies),2),
                          'p95_ms':round(latencies[94],2),'scope':'local purchase service; excludes queue wait and external APIs'}))
    finally:
        await services.close()
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            await conn.close()


if __name__ == '__main__':
    asyncio.run(main())

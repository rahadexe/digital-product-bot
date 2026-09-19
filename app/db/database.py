"""PostgreSQL connection pool shared by every service."""

from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import asyncpg


def normalize_dsn(dsn: str) -> str:
    """asyncpg does not implement channel binding; TLS is still enforced through sslmode."""
    parts = urlsplit(dsn)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "channel_binding"]
    return urlunsplit(parts._replace(query=urlencode(query)))


def affected(status: str) -> int:
    """Row count from an asyncpg command tag such as ``UPDATE 3``."""
    count = status.rsplit(" ", 1)[-1]
    return int(count) if count.isdigit() else 0


class Database:
    """
    Every query is a network round trip, so latency to the database dominates response time.
    Prepared statements are cached per connection (one round trip per query instead of two),
    and connections go back to the pool without asyncpg's reset query (another round trip):
    ``connect()`` always ends open transactions and the application never changes session state.
    """

    def __init__(self, dsn: str, *, schema: str | None = None, max_size: int = 10, statement_cache_size: int = 100):
        # A schema isolates disposable test data; it needs a direct (non-pooled) connection.
        if schema and not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", schema):
            raise ValueError("Invalid schema name.")
        self.dsn = dsn
        self.schema = schema
        self.max_size = max_size
        self.statement_cache_size = statement_cache_size
        self._pool: asyncpg.Pool | None = None
        self._pool_lock = asyncio.Lock()

    async def _init_connection(self, conn: asyncpg.Connection) -> None:
        # Money stays exact in PostgreSQL; application code works with rounded floats.
        await conn.set_type_codec("numeric", encoder=str, decoder=float, schema="pg_catalog", format="text")

    async def _use_schema(self, conn: asyncpg.Connection) -> None:
        await conn.execute(f'SET search_path TO "{self.schema}"')

    async def _keep_session(self, conn: asyncpg.Connection) -> None:
        return None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            async with self._pool_lock:
                if self._pool is None:
                    if not self.dsn:
                        raise RuntimeError("DATABASE_URL is not configured.")
                    self._pool = await asyncpg.create_pool(
                        normalize_dsn(self.dsn),
                        # A few connections stay open: opening one to a remote database (TLS and setup)
                        # takes far longer than a query, and asyncpg would otherwise close idle ones
                        # after five minutes, making the first taps after a quiet spell slow.
                        min_size=min(1, self.max_size),
                        max_size=self.max_size,
                        max_inactive_connection_lifetime=300.0,
                        statement_cache_size=self.statement_cache_size,
                        init=self._init_connection,
                        setup=self._use_schema if self.schema else None,
                        reset=self._keep_session,
                    )
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @asynccontextmanager
    async def connect(self):
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            try:
                yield conn
            finally:
                try:
                    if not conn.is_closed() and conn.is_in_transaction():
                        await conn.execute("ROLLBACK")
                except Exception:
                    pass

    @asynccontextmanager
    async def transaction(self):
        async with self.connect() as conn:
            async with conn.transaction():
                yield conn

    async def ensure_schema(self) -> None:
        if not self.schema:
            return
        async with self.connect() as conn:
            await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
            if await conn.fetchval("SELECT current_schema()") != self.schema:
                raise RuntimeError("Schema isolation needs a direct PostgreSQL connection; poolers drop search_path.")

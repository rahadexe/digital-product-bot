"""Admin login throttling and session revocation, stored in the database so every web process agrees."""

from __future__ import annotations

import time

from app.db import Database

MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 300


class AdminAccessService:
    def __init__(self, db: Database):
        self.db = db

    async def login_allowed(self, client_ip: str) -> bool:
        async with self.db.connect() as conn:
            recent = await conn.fetchval(
                "SELECT COUNT(*) FROM admin_login_attempts "
                "WHERE client_ip = $1 AND attempted_at > now() - make_interval(secs => $2)",
                client_ip,
                LOGIN_WINDOW_SECONDS,
            )
        return recent < MAX_LOGIN_ATTEMPTS

    async def record_attempt(self, client_ip: str) -> None:
        async with self.db.transaction() as conn:
            await conn.execute("DELETE FROM admin_login_attempts WHERE attempted_at < now() - interval '1 day'")
            await conn.execute("INSERT INTO admin_login_attempts (client_ip) VALUES ($1)", client_ip)

    async def clear_attempts(self, client_ip: str) -> None:
        async with self.db.connect() as conn:
            await conn.execute("DELETE FROM admin_login_attempts WHERE client_ip = $1", client_ip)

    async def revoke(self, token_hash: str, expires_at: int) -> None:
        async with self.db.transaction() as conn:
            await conn.execute("DELETE FROM revoked_admin_sessions WHERE expires_at < $1", int(time.time()))
            await conn.execute(
                "INSERT INTO revoked_admin_sessions (token_hash, expires_at) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                token_hash,
                expires_at,
            )

    async def is_revoked(self, token_hash: str) -> bool:
        async with self.db.connect() as conn:
            return bool(await conn.fetchval("SELECT 1 FROM revoked_admin_sessions WHERE token_hash = $1", token_hash))

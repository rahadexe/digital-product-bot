"""Atomic, shared fixed-window budgets; hashed identities avoid storing raw credentials/IPs."""

import hashlib
import math

from app.db import Database


class RateLimits:
    def __init__(self, db: Database):
        self.db = db

    async def consume(self, namespace: str, identity: str, limit: int, seconds: int = 60) -> int:
        """Return zero when allowed, otherwise seconds until the budget resets."""
        key = hashlib.sha256(f'{namespace}:{identity}'.encode()).hexdigest()
        async with self.db.connect() as conn:
            row = await conn.fetchrow(
                "INSERT INTO request_limits(key,hits,expires_at) VALUES($1,1,now()+$3*interval '1 second') "
                "ON CONFLICT(key) DO UPDATE SET "
                "hits=CASE WHEN request_limits.expires_at<=now() THEN 1 ELSE LEAST(request_limits.hits+1,$2+1) END, "
                "expires_at=CASE WHEN request_limits.expires_at<=now() THEN EXCLUDED.expires_at ELSE request_limits.expires_at END "
                "RETURNING hits,EXTRACT(EPOCH FROM expires_at-now()) AS remaining", key,limit,seconds,
            )
        return max(1, math.ceil(row['remaining'])) if row['hits'] > limit else 0

"""One HTTP connection pool per service, reused across gateway requests."""

import httpx


def gateway_http(timeout: float = 20.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=5, pool=5),
        limits=httpx.Limits(max_connections=16, max_keepalive_connections=8, keepalive_expiry=60),
        follow_redirects=False,
    )

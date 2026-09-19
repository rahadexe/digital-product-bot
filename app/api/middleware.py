"""Request boundaries applied before routing: rate and size limits, Origin checks and security headers."""

from __future__ import annotations

import asyncio
import ipaddress
import time
from collections import OrderedDict, deque

from fastapi.responses import JSONResponse

from app.core.config import Settings

RATE_LIMIT_PER_MINUTE = 180
# Public paths that read the database; the Telegram webhook is excluded because every update
# arrives from Telegram's few addresses and is already guarded by its secret.
LIMITED_PREFIXES = ('/api/', '/health/')
# Cloudflare's published edge ranges (https://www.cloudflare.com/ips/). Only a request whose connecting peer is
# one of these may name the visitor through CF-Connecting-IP; anyone reaching the server directly cannot.
CLOUDFLARE_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22', '103.31.4.0/22', '141.101.64.0/18',
        '108.162.192.0/18', '190.93.240.0/20', '188.114.96.0/20', '197.234.240.0/22', '198.41.128.0/17',
        '162.158.0.0/15', '104.16.0.0/13', '104.24.0.0/14', '172.64.0.0/13', '131.0.72.0/22',
        '2400:cb00::/32', '2606:4700::/32', '2803:f800::/32', '2405:b500::/32', '2405:8100::/32',
        '2a06:98c0::/29', '2c0f:f248::/32',
    )
)


def _ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def visitor_ip(scope) -> str:
    """The visitor's address. Uvicorn has already resolved trusted proxies; a Cloudflare edge is resolved here."""
    peer = (scope.get('client') or ('unknown', 0))[0]
    peer_ip = _ip(peer)
    if peer_ip is not None and any(peer_ip in net for net in CLOUDFLARE_NETWORKS):
        for key, value in scope.get('headers', []):
            if key == b'cf-connecting-ip':
                named = _ip(value.decode('latin-1'))
                if named is not None:
                    return str(named)
    return peer


def _is_internal(address: str) -> bool:
    ip = _ip(address)
    return ip is not None and (ip.is_loopback or ip.is_private)
MAX_BODY_BYTES = 2 * 1024 * 1024
BODY_TIMEOUT_SECONDS = 15
TRACKED_CLIENTS = 10000


class SecurityBoundary:
    """
    The rate limit is per process; put a proxy-level limit in front when running several
    web replicas. Login throttling is stored in the database and is shared.
    """

    def __init__(self, app, settings: Settings):
        self.app = app
        self.production = settings.app_env == 'production'
        self.allowed_origins = set(Settings.split(settings.allowed_origins))
        if not self.production:
            self.allowed_origins |= {f'http://{host}:{port}' for host in ('localhost', '127.0.0.1') for port in (3000, 3001)}
        self.hits: OrderedDict[str, deque] = OrderedDict()

    def _headers(self, path: str, api: bool) -> list[tuple[bytes, bytes]]:
        extra = [(b'x-content-type-options', b'nosniff'), (b'referrer-policy', b'no-referrer')]
        if api:
            extra.append((b'cache-control', b'no-store'))
        if self.production:
            extra.append((b'strict-transport-security', b'max-age=31536000'))
        ancestors = (
            "'self' https://web.telegram.org https://*.telegram.org" if path == '/app' or path.startswith('/app/') else "'none'"
        )
        connect = "'self'" if self.production else "'self' http://localhost:8000 http://127.0.0.1:8000"
        csp = (
            "default-src 'self'; script-src 'self' 'unsafe-inline' https://telegram.org; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; "
            f"connect-src {connect}; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors {ancestors}"
        )
        extra.append((b'content-security-policy', csp.encode()))
        return extra

    def _rate_limited(self, client: str) -> bool:
        now = time.monotonic()
        bucket = self.hits.setdefault(client, deque())
        self.hits.move_to_end(client)
        while bucket and bucket[0] < now - 60:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT_PER_MINUTE:
            return True
        bucket.append(now)
        if len(self.hits) > TRACKED_CLIENTS:
            self.hits.popitem(last=False)
        return False

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        path = scope['path']
        api = path.startswith('/api/')
        security_headers = self._headers(path, api)
        # Everything after this (rate limits, login throttling, audit entries) sees the visitor, not Cloudflare.
        client = visitor_ip(scope)
        if scope.get('client') and client != scope['client'][0]:
            scope['client'] = (client, scope['client'][1])

        async def secured_send(message):
            if message['type'] == 'http.response.start':
                message['headers'] = list(message.get('headers', [])) + security_headers
            await send(message)

        limited = path.startswith(LIMITED_PREFIXES) and not (path.startswith('/health/') and _is_internal(client))
        if limited and self._rate_limited(client):
            response = JSONResponse({'detail': 'Too many requests. Try again shortly.'}, 429, headers={'Retry-After': '60'})
            return await response(scope, receive, secured_send)

        if not (api and scope['method'] in {'POST', 'PUT', 'PATCH', 'DELETE'}):
            return await self.app(scope, receive, secured_send)

        headers = {key.decode('latin-1').lower(): value.decode('latin-1') for key, value in scope.get('headers', [])}
        origin = headers.get('origin')
        expected = f"{scope.get('scheme', 'http')}://{headers.get('host', '')}"
        if origin and origin != expected and origin not in self.allowed_origins:
            return await JSONResponse({'detail': 'Origin not allowed.'}, 403)(scope, receive, secured_send)

        body = bytearray()
        while True:
            try:
                message = await asyncio.wait_for(receive(), timeout=BODY_TIMEOUT_SECONDS)
            except TimeoutError:
                return await JSONResponse({'detail': 'Request timed out.'}, 408)(scope, receive, secured_send)
            if message['type'] == 'http.disconnect':
                return None
            body.extend(message.get('body', b''))
            if len(body) > MAX_BODY_BYTES:
                return await JSONResponse({'detail': 'Request body is too large.'}, 413)(scope, receive, secured_send)
            if not message.get('more_body'):
                break

        delivered = False

        async def buffered_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()

        return await self.app(scope, buffered_receive, secured_send)

"""Admin sessions: a signed HttpOnly cookie plus a CSRF header, revocable through the database."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Annotated, Any

import jwt
from fastapi import Depends, HTTPException, Request
from jwt import PyJWTError

from app.api.deps import ServicesDep
from app.services import Services

SESSION_COOKIE_NAME = "shop_admin_session"
CSRF_HEADER_NAME = "x-csrf-token"
SESSION_SECONDS = 90 * 24 * 3600  # 90 days persistent admin session
ALGORITHM = "HS256"


class AdminAuth:
    def __init__(self, secret_key: str, admin_password: str):
        # Changing the password invalidates every session signed with the old one.
        self.secret_key = hmac.new(secret_key.encode(), admin_password.encode(), hashlib.sha256).hexdigest()
        self.admin_password = admin_password

    def verify_password(self, plain_password: str) -> bool:
        if not self.admin_password:
            return False
        return hmac.compare_digest(plain_password.encode(), self.admin_password.encode())

    def create_session_token(self) -> str:
        now = int(time.time())
        payload = {"sub": "admin", "iat": now, "exp": now + SESSION_SECONDS, "nonce": secrets.token_hex(16)}
        return jwt.encode(payload, self.secret_key, algorithm=ALGORITHM)

    def _claims(self, token: str) -> dict[str, Any] | None:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[ALGORITHM], options={"require": ["exp", "iat", "sub"]})
        except PyJWTError:
            return None
        return payload if payload.get("sub") == "admin" else None

    def verify_session_token(self, token: str) -> bool:
        return self._claims(token) is not None

    def expiry(self, token: str) -> int | None:
        claims = self._claims(token)
        return int(claims["exp"]) if claims else None

    def get_csrf_token(self, session_token: str) -> str:
        return hmac.new(self.secret_key.encode(), f"csrf:{session_token}".encode(), hashlib.sha256).hexdigest()

    def verify_csrf(self, session_token: str, csrf_token: str) -> bool:
        if not session_token or not csrf_token:
            return False
        return hmac.compare_digest(self.get_csrf_token(session_token).encode(), csrf_token.encode())


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    return header.split(" ", 1)[1] if header.startswith("Bearer ") else None


def get_admin_auth(request: Request) -> AdminAuth:
    return request.app.state.admin_auth


AuthDep = Annotated[AdminAuth, Depends(get_admin_auth)]


async def session_is_active(services: Services, auth: AdminAuth, token: str | None) -> bool:
    return bool(token) and auth.verify_session_token(token) and not await services.admin_access.is_revoked(token_hash(token))


async def require_admin(request: Request, services: ServicesDep, auth: AuthDep) -> None:
    token = request.cookies.get(SESSION_COOKIE_NAME) or bearer_token(request)
    if not await session_is_active(services, auth, token):
        raise HTTPException(status_code=401, detail="Authentication required.")


async def require_write(request: Request, services: ServicesDep, auth: AuthDep) -> None:
    """Cookie sessions must send the CSRF header; a valid bearer token is an explicit credential."""
    bearer = bearer_token(request)
    if bearer and await session_is_active(services, auth, bearer):
        return
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    csrf = request.headers.get(CSRF_HEADER_NAME)
    if not cookie or not csrf or not auth.verify_csrf(cookie, csrf) or not await session_is_active(services, auth, cookie):
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token.")


WRITE = [Depends(require_write)]

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.admin.auth import (
    SESSION_COOKIE_NAME,
    SESSION_SECONDS,
    WRITE,
    AuthDep,
    bearer_token,
    session_is_active,
    token_hash,
)
from app.api.admin.schemas import LoginPayload
from app.api.deps import ServicesDep, client_ip
from app.services.audit import record

router = APIRouter()


@router.post("/login")
async def login(payload: LoginPayload, request: Request, response: Response, services: ServicesDep, auth: AuthDep):
    ip = client_ip(request)
    if not await services.admin_access.login_allowed(ip):
        async with services.db.connect() as conn:
            await record(conn, "login_rate_limited", f"Admin login blocked from {ip}")
        raise HTTPException(429, "Too many attempts. Try again in five minutes.", headers={"Retry-After": "300"})
    await services.admin_access.record_attempt(ip)
    if not auth.verify_password(payload.password):
        async with services.db.connect() as conn:
            await record(conn, "login_failed", f"Invalid admin password from {ip}")
        raise HTTPException(status_code=401, detail="Invalid admin password.")
    await services.admin_access.clear_attempts(ip)

    token = auth.create_session_token()
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=services.config.cookie_secure,
        samesite="lax",
        max_age=SESSION_SECONDS,
        path="/",
    )
    return {"success": True, "csrf": auth.get_csrf_token(token)}


@router.get("/session")
async def session(request: Request, services: ServicesDep, auth: AuthDep):
    token = request.cookies.get(SESSION_COOKIE_NAME) or bearer_token(request)
    if await session_is_active(services, auth, token):
        return {"signed_in": True, "csrf": auth.get_csrf_token(token)}
    return {"signed_in": False, "csrf": ""}


@router.post("/logout", dependencies=WRITE)
async def logout(request: Request, response: Response, services: ServicesDep, auth: AuthDep):
    for token in {request.cookies.get(SESSION_COOKIE_NAME), bearer_token(request)} - {None}:
        expires_at = auth.expiry(token)
        if expires_at:
            await services.admin_access.revoke(token_hash(token), expires_at)
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return {"success": True}

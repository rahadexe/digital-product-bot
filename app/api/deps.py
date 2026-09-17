from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.services import Services


def get_services(request: Request) -> Services:
    return request.app.state.services


ServicesDep = Annotated[Services, Depends(get_services)]


def client_ip(request: Request) -> str:
    # Uvicorn applies X-Forwarded-For only when the peer is in TRUSTED_PROXY_IPS.
    return request.client.host if request.client else "unknown"

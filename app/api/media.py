"""Public images uploaded in the admin console, served outside /api so browsers and Telegram can cache them."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import Response

from app.api.deps import ServicesDep

router = APIRouter(tags=["media"])

POSTGRES_BIGINT_MAX = 2**63 - 1


@router.get("/media/banners/{banner_id}")
async def home_banner(services: ServicesDep, request: Request, banner_id: int = Path(..., gt=0, le=POSTGRES_BIGINT_MAX)):
    image = await services.media.banner_image(banner_id)
    if image is None:
        raise HTTPException(404, "Banner not found.")
    data, content_type, version = image
    etag = f'"banner-{banner_id}-{version}"'
    # The storefront always links a versioned URL, so a copy can be kept for as long as the browser likes.
    headers = {"ETag": etag, "Cache-Control": "public, max-age=31536000, immutable"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=data, media_type=content_type, headers=headers)


@router.get("/media/welcome-banner")
async def welcome_banner(services: ServicesDep, request: Request):
    banner = await services.media.get_welcome_banner()
    if banner is None:
        raise HTTPException(404, "Welcome banner not found.")
    data, content_type, _w, _h, version = banner
    etag = f'"welcome-banner-{version}"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=31536000, immutable"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=data, media_type=content_type, headers=headers)


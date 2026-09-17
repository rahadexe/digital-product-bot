from __future__ import annotations

from fastapi import APIRouter, Body, File, HTTPException, Path, UploadFile

from app.api.admin.auth import WRITE
from app.api.deps import ServicesDep
from app.services.media import BANNER_RECOMMENDED, MAX_BANNERS, MAX_IMAGE_BYTES

router = APIRouter()

POSTGRES_BIGINT_MAX = 2**63 - 1


@router.get("/settings")
async def read_settings(services: ServicesDep):
    # Secret settings are write-only and never returned.
    return await services.settings.public()


@router.post("/settings", dependencies=WRITE)
async def update_settings(services: ServicesDep, payload: dict[str, str] = Body(...)):
    if len(payload) > 100 or any(len(key) > 80 or len(value) > 16000 for key, value in payload.items()):
        raise HTTPException(422, "Settings exceed the supported size.")
    changed = await services.settings.update(payload)
    if any(k.startswith("binance_") for k in payload):
        await services.deposits.get_or_create_binance_method()
    return {"success": True, "changed": changed}


@router.get("/settings/banners")
async def read_banners(services: ServicesDep):
    return {
        "banners": await services.media.banners(),
        "recommended": BANNER_RECOMMENDED,
        "max_bytes": MAX_IMAGE_BYTES,
        "max_count": MAX_BANNERS,
    }


@router.post("/settings/banners", dependencies=WRITE)
async def add_banner(services: ServicesDep, file: UploadFile = File(...)):
    # One byte past the limit is enough to know the file is too large.
    data = await file.read(MAX_IMAGE_BYTES + 1)
    return {"success": True, "banner": await services.media.add_banner(data)}


@router.delete("/settings/banners/{banner_id}", dependencies=WRITE)
async def remove_banner(services: ServicesDep, banner_id: int = Path(..., gt=0, le=POSTGRES_BIGINT_MAX)):
    if not await services.media.remove_banner(banner_id):
        raise HTTPException(404, "Banner not found.")
    return {"success": True}


@router.get("/settings/welcome-banner")
async def read_welcome_banner(services: ServicesDep):
    banner = await services.media.get_welcome_banner()
    if not banner:
        return {"has_banner": False, "url": None}
    _data, content_type, width, height, version = banner
    return {
        "has_banner": True,
        "url": f"/media/welcome-banner?v={version}",
        "width": width,
        "height": height,
        "content_type": content_type,
    }


@router.post("/settings/welcome-banner", dependencies=WRITE)
async def upload_welcome_banner(services: ServicesDep, file: UploadFile = File(...)):
    max_bytes = 5 * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(400, "The image file is larger than 5 MB.")
    from app.services.errors import InvalidInputError
    try:
        result = await services.media.set_welcome_banner(data)
    except InvalidInputError as e:
        raise HTTPException(400, str(e))
    return {"success": True, "banner": result}


@router.delete("/settings/welcome-banner", dependencies=WRITE)
async def delete_welcome_banner(services: ServicesDep):
    await services.media.remove_welcome_banner()
    return {"success": True}


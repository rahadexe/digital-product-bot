"""FastAPI application: admin API, Mini App storefront API, health checks and the static console."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import admin, health, payments, reseller, telegram
from app.api.admin.auth import AdminAuth
from app.api.errors import register_error_handlers
from app.api.middleware import SecurityBoundary
from app.core.config import BASE_DIR, Settings
from app.services import Services

CONSOLE_OUT_DIR = BASE_DIR / "console" / "out"
DEV_CONSOLE_ORIGINS = ["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"]


class ConsoleFiles(StaticFiles):
    """Pages are always re-fetched; the files they name carry a hash, so they can be kept forever.

    A page held in a cache after a deploy asks for scripts and styles that no longer exist, and the
    console loads as bare text. Telling the browser and the CDN which is which prevents that.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        path = str(getattr(response, "path", ""))
        hashed = "/_next/static/" in path.replace("\\", "/")
        response.headers["cache-control"] = "public, max-age=31536000, immutable" if hashed else "no-cache"
        return response


def create_app(services: Services) -> FastAPI:
    config = services.config
    production = config.app_env == "production"
    app = FastAPI(
        title="SubsMarket API",
        docs_url=None if production else "/docs",
        redoc_url=None,
        openapi_url=None if production else "/openapi.json",
    )
    app.state.services = services
    app.state.admin_auth = AdminAuth(config.secret_key, config.admin_password)

    # Added innermost first: Starlette runs the last one added outermost. CORS must wrap
    # SecurityBoundary, or a rejection it returns itself (429, 413, 408) reaches a cross-origin
    # console without Access-Control-Allow-Origin and the browser reports an opaque CORS failure
    # instead of the real status and Retry-After.
    app.add_middleware(SecurityBoundary, settings=config, rate_limits=services.rate_limits)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=Settings.split(config.allowed_origins) + ([] if production else DEV_CONSOLE_ORIGINS),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Container health checks reach the app as localhost, whatever public domain ALLOWED_HOSTS names.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=Settings.split(config.allowed_hosts) + ["localhost", "127.0.0.1"])
    register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(telegram.router)
    app.include_router(admin.router)
    app.include_router(payments.router)
    app.include_router(reseller.router)

    @app.get('/app/', include_in_schema=False)
    async def legacy_payment_return(payment: str = ''):
        # Existing invoices can still carry the old return URL after deployment.
        from urllib.parse import urlencode
        return RedirectResponse('/api/payments/return?' + urlencode({'reference': payment}), status_code=302)

    if CONSOLE_OUT_DIR.is_dir():
        app.mount("/", ConsoleFiles(directory=CONSOLE_OUT_DIR, html=True), name="console")
    return app

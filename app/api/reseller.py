"""Reseller API Gateway: authentication, catalog sync, instant order fulfillment, and developer documentation."""

from __future__ import annotations

import logging
from html import escape
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import ServicesDep

logger = logging.getLogger("app.api.reseller")

router = APIRouter(prefix="/api/v1/reseller", tags=["Reseller API"])


class ResellerOrderPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    product_id: int = Field(..., strict=True, gt=0, le=9223372036854775807, description="Product ID to purchase")
    quantity: int = Field(default=1, strict=True, ge=1, le=100, description="Quantity to purchase (1-100)")
    custom_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Unique merchant reference, required unless Idempotency-Key header is supplied. Reuse on retry.",
    )
    customer_input: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional customer input (e.g., Gmail address, invite details)",
    )


async def get_reseller_user(
    request: Request,
    services: ServicesDep,
    x_api_key: Annotated[Optional[str], Header(alias="X-API-Key")] = None,
    authorization: Annotated[Optional[str], Header()] = None,
) -> dict[str, Any]:
    """
    Authenticate a reseller request via X-API-Key header or Authorization: Bearer <token>.
    """
    api_key: str | None = None
    if x_api_key and x_api_key.strip():
        api_key = x_api_key.strip()
    elif authorization and authorization.strip():
        parts = authorization.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].lower() in {"bearer", "token", "apikey"}:
            api_key = parts[1].strip()
        else:
            api_key = parts[0].strip()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key. Provide via 'X-API-Key' header or 'Authorization: Bearer <key>'.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    reseller = await services.reseller.authenticate_key(api_key)
    if not reseller:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or revoked API Key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if reseller.get("is_banned"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is suspended or banned.",
        )

    write = request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}
    retry = await services.rate_limits.consume('reseller-write' if write else 'reseller-read',
                                               str(reseller['tg_user_id']), 30 if write else 120)
    if retry:
        raise HTTPException(429, 'Request limit reached. Retry after the indicated delay.', headers={'Retry-After': str(retry)})
    return reseller


ResellerDep = Annotated[dict[str, Any], Depends(get_reseller_user)]


@router.get("/me")
async def get_reseller_profile(reseller: ResellerDep, services: ServicesDep):
    """Fetch reseller wallet balance, rank, profile details, and API key info."""
    settings_vals = await services.settings.values()
    symbol = settings_vals.get("currency_symbol", "৳")
    currency = settings_vals.get("currency", "BDT")

    # Refresh live balance directly from database
    user_row = await services.users.get(reseller["tg_user_id"])
    balance = float(user_row["balance"]) if user_row else float(reseller["balance"])
    total_spent = float(user_row["total_spent"]) if user_row else float(reseller["total_spent"])

    return {
        "success": True,
        "user": {
            "user_id": reseller["user_id"],
            "tg_user_id": reseller["tg_user_id"],
            "username": reseller.get("username"),
            "name": f"{reseller.get('first_name') or ''} {reseller.get('last_name') or ''}".strip() or "User",
            "rank": reseller.get("rank") or "Standard",
            "balance": balance,
            "currency": currency,
            "currency_symbol": symbol,
            "total_spent": total_spent,
        },
        "api_key": {
            "prefix": reseller["key_prefix"],
            "created_at": reseller["key_created_at"].isoformat() if reseller.get("key_created_at") else None,
            "last_used_at": reseller["last_used_at"].isoformat() if reseller.get("last_used_at") else None,
        },
    }


@router.get("/products")
async def list_reseller_products(
    reseller: ResellerDep,
    services: ServicesDep,
    category_id: Optional[int] = Query(None, gt=0, description="Optional category filter"),
):
    """List all active products with real-time stock and special reseller wholesale pricing."""
    settings_vals = await services.settings.values()
    symbol = settings_vals.get("currency_symbol", "৳")
    currency = settings_vals.get("currency", "BDT")

    products = await services.reseller.get_reseller_products(
        category_id=category_id, is_reseller=(reseller.get('rank') or '').strip().lower() in {'reseller', 'reseller partner'},
    )
    return {
        "success": True,
        "count": len(products),
        "currency": currency,
        "currency_symbol": symbol,
        "products": products,
    }


@router.get("/products/{product_id}")
async def get_reseller_product(product_id: int, reseller: ResellerDep, services: ServicesDep):
    """Retrieve single product details with live stock availability and reseller wholesale price."""
    settings_vals = await services.settings.values()
    symbol = settings_vals.get("currency_symbol", "৳")
    currency = settings_vals.get("currency", "BDT")

    product = await services.reseller.get_reseller_product(
        product_id, is_reseller=(reseller.get('rank') or '').strip().lower() in {'reseller', 'reseller partner'},
    )
    if not product:
        raise HTTPException(status_code=404, detail="Product not found or currently inactive.")

    return {
        "success": True,
        "currency": currency,
        "currency_symbol": symbol,
        "product": product,
    }


@router.post("/orders")
async def create_reseller_order(
    payload: ResellerOrderPayload,
    reseller: ResellerDep,
    services: ServicesDep,
    idempotency_key: Annotated[str | None, Header(alias='Idempotency-Key', max_length=64)] = None,
):
    """
    Purchase a product programmatically at discounted reseller pricing (or normal pricing for non-resellers).
    Deducts balance atomically from wallet and immediately returns delivered credentials in response.
    """
    tg_user_id = reseller["tg_user_id"]
    request_id = (payload.custom_id or idempotency_key or '').strip()
    if payload.custom_id and idempotency_key and payload.custom_id.strip() != idempotency_key.strip():
        raise HTTPException(422, 'custom_id and Idempotency-Key must match when both are supplied.')
    if not request_id:
        raise HTTPException(422, 'Supply custom_id or Idempotency-Key and reuse it when retrying this order.')
    settings_vals = await services.settings.values()
    currency = settings_vals.get("currency", "BDT")
    symbol = settings_vals.get("currency_symbol", "৳")

    # Verify store not paused
    paused = await services.settings.paused_message()
    if paused:
        raise HTTPException(status_code=503, detail=paused)

    # Execute atomic purchase
    success, message, order_data = await services.purchases.purchase(
        tg_user_id=tg_user_id,
        product_id=payload.product_id,
        quantity=payload.quantity,
        request_id=request_id,
        require_reseller=False,
        reseller_key_id=reseller['key_id'],
        customer_input=payload.customer_input or "",
    )

    if not success or not order_data:
        # Determine status code: balance issue -> 400, not found -> 404, stock -> 400
        status_code = 400
        if "not found" in message.lower() or "unavailable" in message.lower():
            status_code = 404
        elif "insufficient balance" in message.lower():
            status_code = 400
        elif 'no longer active' in message.lower() or 'banned' in message.lower():
            status_code = 403
        raise HTTPException(status_code=status_code, detail=message)

    is_delivered = order_data.get("fulfillment") == "delivered"
    return {
        "success": True,
        "order_id": order_data["order_id"],
        "custom_id": request_id,
        "product_id": payload.product_id,
        "product_title": order_data["product_title"],
        "quantity": payload.quantity,
        "unit_price": float(order_data.get('unit_price') or order_data['price'] / payload.quantity),
        "total_price": float(order_data["price"]),
        "currency": currency,
        "currency_symbol": symbol,
        "balance_after": float(order_data["remaining_balance"]),
        "fulfillment": order_data["fulfillment"],
        "credentials": order_data["delivered_item"] if is_delivered else None,
        "created_at": order_data["created_at"].isoformat() if hasattr(order_data["created_at"], "isoformat") else str(order_data["created_at"]),
        "message": "Order delivered instantly." if is_delivered else "Order accepted. Manual delivery in progress.",
    }


@router.get("/orders/{order_id}")
async def get_reseller_order(order_id: int, reseller: ResellerDep, services: ServicesDep):
    """Query an order placed by this reseller to inspect credentials and fulfillment status."""
    order = await services.reseller.get_reseller_order(reseller["tg_user_id"], order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    return {
        "success": True,
        "order": order,
    }


@router.get("/orders")
async def list_reseller_orders(
    reseller: ResellerDep,
    services: ServicesDep,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List recent orders placed by this reseller with pagination."""
    orders = await services.reseller.get_reseller_orders(reseller["tg_user_id"], limit=limit, offset=offset)
    return {
        "success": True,
        "count": len(orders),
        "limit": limit,
        "offset": offset,
        "orders": orders,
    }


@router.get("/openapi.json", include_in_schema=False)
async def reseller_openapi_spec(request: Request, services: ServicesDep):
    """Machine-readable OpenAPI 3.1.0 specification for AI Agents and automated integrations."""
    settings_vals = await services.settings.values()
    store_name = settings_vals.get("store_name", "Premium Store")
    base_url = str(request.base_url).rstrip("/")
    api_base = f"{base_url}/api/v1/reseller"

    return {
        "openapi": "3.1.0",
        "info": {
            "title": f"{store_name} Reseller API",
            "version": "1.0.0",
            "description": (
                "Automated wholesale catalog sync and instant order fulfillment gateway for resellers, "
                "e-commerce platforms, and autonomous AI agents. Authenticate every request using the "
                "X-API-Key header with an active key formatted as rklive followed by 32 alphanumeric characters."
            ),
        },
        "servers": [
            {
                "url": api_base,
                "description": "Reseller API Gateway",
            }
        ],
        "security": [
            {"ApiKeyAuth": []}
        ],
        "paths": {
            "/me": {
                "get": {
                    "summary": "Get Reseller Profile and Wallet Balance",
                    "description": "Inspect your account rank (Member or Reseller), live wallet balance, currency, and API key metadata.",
                    "operationId": "getResellerProfile",
                    "responses": {
                        "200": {
                            "description": "Profile details returned successfully.",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean"},
                                            "user": {
                                                "type": "object",
                                                "properties": {
                                                    "user_id": {"type": "integer"},
                                                    "tg_user_id": {"type": "integer"},
                                                    "username": {"type": "string", "nullable": True},
                                                    "name": {"type": "string"},
                                                    "rank": {"type": "string"},
                                                    "balance": {"type": "number"},
                                                    "currency": {"type": "string"},
                                                    "currency_symbol": {"type": "string"},
                                                    "total_spent": {"type": "number"},
                                                },
                                            },
                                            "api_key": {
                                                "type": "object",
                                                "properties": {
                                                    "prefix": {"type": "string"},
                                                    "created_at": {"type": "string", "nullable": True},
                                                    "last_used_at": {"type": "string", "nullable": True},
                                                },
                                            },
                                        },
                                    }
                                }
                            },
                        },
                        "401": {"description": "Missing, invalid, or revoked API Key."},
                    },
                }
            },
            "/products": {
                "get": {
                    "summary": "List Catalog Products & Real-Time Stock",
                    "description": "Browse active products with live inventory count and wholesale reseller pricing.",
                    "operationId": "listResellerProducts",
                    "parameters": [
                        {
                            "name": "category_id",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer"},
                            "description": "Optional category filter ID",
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "List of active products with stock and pricing.",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean"},
                                            "count": {"type": "integer"},
                                            "currency": {"type": "string"},
                                            "currency_symbol": {"type": "string"},
                                            "products": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "id": {"type": "integer"},
                                                        "title": {"type": "string"},
                                                        "category_id": {"type": "integer"},
                                                        "category_name": {"type": "string"},
                                                        "regular_price": {"type": "number"},
                                                        "reseller_price": {"type": "number"},
                                                        "has_discount": {"type": "boolean"},
                                                        "discount_percent": {"type": "number"},
                                                        "stock": {"type": "integer"},
                                                        "in_stock": {"type": "boolean"},
                                                        "delivery_type": {"type": "string"},
                                                        "duration": {"type": "string", "nullable": True},
                                                        "icon": {"type": "string", "nullable": True},
                                                    },
                                                },
                                            },
                                        },
                                    }
                                }
                            },
                        },
                        "401": {"description": "Missing or invalid API key."},
                    },
                }
            },
            "/products/{product_id}": {
                "get": {
                    "summary": "Get Single Product Details",
                    "description": "Retrieve pricing and live stock for a specific product ID before placing an order.",
                    "operationId": "getResellerProduct",
                    "parameters": [
                        {
                            "name": "product_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                            "description": "Product ID to inspect",
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Product details.",
                        },
                        "404": {"description": "Product not found or inactive."},
                    },
                }
            },
            "/orders": {
                "post": {
                    "summary": "Create Purchase Order with Instant Fulfillment",
                    "description": (
                        "Purchase a product at wholesale reseller price. Deducts balance from wallet. "
                        "For instant delivery products, credentials (license keys, login accounts) are immediately returned in the response."
                    ),
                    "operationId": "createResellerOrder",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["product_id", "custom_id"],
                                    "properties": {
                                        "product_id": {"type": "integer", "description": "Target product ID"},
                                        "quantity": {"type": "integer", "default": 1, "description": "Quantity (1-100)"},
                                        "custom_id": {
                                            "type": "string",
                                            "description": "Unique merchant order reference for idempotency and safe retries (1-64 characters)",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Order placed successfully and fulfilled.",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "success": {"type": "boolean"},
                                            "order_id": {"type": "integer"},
                                            "custom_id": {"type": "string"},
                                            "product_id": {"type": "integer"},
                                            "product_title": {"type": "string"},
                                            "quantity": {"type": "integer"},
                                            "unit_price": {"type": "number"},
                                            "total_price": {"type": "number"},
                                            "currency": {"type": "string"},
                                            "currency_symbol": {"type": "string"},
                                            "balance_after": {"type": "number"},
                                            "fulfillment": {"type": "string"},
                                            "credentials": {"type": "string", "nullable": True},
                                            "created_at": {"type": "string"},
                                            "message": {"type": "string"},
                                        },
                                    }
                                }
                            },
                        },
                        "400": {"description": "Insufficient balance or out of stock."},
                        "404": {"description": "Product not found."},
                        "422": {"description": "Validation error or missing idempotency reference."},
                    },
                },
                "get": {
                    "summary": "List Recent Reseller Orders",
                    "description": "Query orders previously placed using this account.",
                    "operationId": "listResellerOrders",
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "default": 20},
                            "description": "Number of records to return (1-100)",
                        },
                        {
                            "name": "offset",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "integer", "default": 0},
                            "description": "Offset pagination skip count",
                        },
                    ],
                    "responses": {
                        "200": {"description": "Paginated list of orders."},
                    },
                },
            },
            "/orders/{order_id}": {
                "get": {
                    "summary": "Get Order Credentials and Status",
                    "description": "Query order status and re-fetch credentials for any order placed by your account.",
                    "operationId": "getResellerOrder",
                    "parameters": [
                        {
                            "name": "order_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer"},
                            "description": "Order ID to look up",
                        }
                    ],
                    "responses": {
                        "200": {"description": "Order details with credentials."},
                        "404": {"description": "Order not found."},
                    },
                }
            },
        },
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                    "description": "Secret API Key starting with rklive followed by 32 alphanumeric characters.",
                }
            }
        },
    }


@router.get("/docs", response_class=HTMLResponse, include_in_schema=False)
async def reseller_documentation_page(request: Request, services: ServicesDep):
    """Interactive, developer & AI agent documentation portal with OpenAPI 3.1.0 integration."""
    settings_vals = await services.settings.values()
    store_name = escape(settings_vals.get("store_name", "Premium Store"))
    currency = escape(settings_vals.get("currency", "BDT"))
    symbol = escape(settings_vals.get("currency_symbol", "৳"))
    bot_user = escape(await services.notifier.bot_username(), quote=True)
    base_url = escape(str(request.base_url).rstrip("/"), quote=True)
    api_base = f"{base_url}/api/v1/reseller"
    openapi_url = f"{api_base}/openapi.json"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{store_name} — Reseller & Developer API Docs</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #090d16;
      --card-bg: #111726;
      --card-border: #1e293b;
      --card-hover: #162035;
      --text: #cbd5e1;
      --text-bold: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --primary-glow: rgba(56, 189, 248, 0.15);
      --accent: #10b981;
      --accent-glow: rgba(16, 185, 129, 0.15);
      --warning: #f59e0b;
      --danger: #ef4444;
      --code-bg: #070a10;
      --tag-get: rgba(56, 189, 248, 0.15);
      --tag-get-text: #38bdf8;
      --tag-post: rgba(16, 185, 129, 0.15);
      --tag-post-text: #34d399;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 0 16px 80px;
    }}
    .container {{
      max-width: 980px;
      margin: 0 auto;
    }}
    header {{
      padding: 48px 0 28px;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 32px;
    }}
    .header-top {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 16px;
      margin-bottom: 16px;
    }}
    .badges {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 12px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
      background: var(--primary-glow);
      color: var(--primary);
      border: 1px solid rgba(56, 189, 248, 0.3);
    }}
    .badge.agent {{
      background: var(--accent-glow);
      color: var(--accent);
      border-color: rgba(16, 185, 129, 0.3);
    }}
    .quick-links {{
      display: flex;
      gap: 10px;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 7px 14px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      text-decoration: none;
      transition: all 0.15s ease;
      cursor: pointer;
    }}
    .btn-primary {{
      background: #0284c7;
      color: #ffffff;
      border: 1px solid #38bdf8;
    }}
    .btn-primary:hover {{
      background: #0369a1;
    }}
    .btn-outline {{
      background: transparent;
      color: var(--text);
      border: 1px solid var(--card-border);
    }}
    .btn-outline:hover {{
      background: var(--card-bg);
      border-color: var(--text-muted);
    }}
    h1 {{
      font-size: 32px;
      font-weight: 800;
      color: var(--text-bold);
      letter-spacing: -0.5px;
      margin-bottom: 10px;
    }}
    header p {{
      color: var(--text-muted);
      font-size: 16px;
      max-width: 760px;
    }}
    nav.toc {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin-top: 24px;
      padding-top: 20px;
      border-top: 1px solid var(--card-border);
    }}
    nav.toc a {{
      color: var(--text-muted);
      text-decoration: none;
      font-size: 13px;
      font-weight: 500;
      padding: 4px 10px;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.03);
      transition: all 0.15s ease;
    }}
    nav.toc a:hover {{
      color: var(--text-bold);
      background: rgba(255, 255, 255, 0.08);
    }}
    h2 {{
      font-size: 22px;
      font-weight: 700;
      color: var(--text-bold);
      margin: 44px 0 16px;
      display: flex;
      align-items: center;
      gap: 10px;
      letter-spacing: -0.3px;
    }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 24px;
    }}
    .card-highlight {{
      border-color: rgba(56, 189, 248, 0.4);
      background: linear-gradient(180deg, rgba(56, 189, 248, 0.05) 0%, rgba(17, 23, 38, 1) 100%);
    }}
    .card-agent {{
      border-color: rgba(16, 185, 129, 0.4);
      background: linear-gradient(180deg, rgba(16, 185, 129, 0.06) 0%, rgba(17, 23, 38, 1) 100%);
    }}
    .step {{
      display: flex;
      gap: 16px;
      margin-bottom: 18px;
    }}
    .step:last-child {{
      margin-bottom: 0;
    }}
    .step-num {{
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: #0284c7;
      color: #ffffff;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 13px;
      flex-shrink: 0;
    }}
    .step-content {{
      flex: 1;
    }}
    .step-content h3 {{
      font-size: 15px;
      color: var(--text-bold);
      margin-bottom: 4px;
    }}
    .endpoint {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      margin-bottom: 20px;
      overflow: hidden;
    }}
    .endpoint-header {{
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 16px 20px;
      background: rgba(255, 255, 255, 0.02);
      border-bottom: 1px solid var(--card-border);
    }}
    .method {{
      font-size: 12px;
      font-weight: 700;
      padding: 4px 8px;
      border-radius: 6px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .method.get {{
      background: var(--tag-get);
      color: var(--tag-get-text);
      border: 1px solid rgba(56, 189, 248, 0.4);
    }}
    .method.post {{
      background: var(--tag-post);
      color: var(--tag-post-text);
      border: 1px solid rgba(16, 185, 129, 0.4);
    }}
    .path {{
      font-family: 'Fira Code', monospace;
      font-size: 14px;
      font-weight: 600;
      color: var(--text-bold);
    }}
    .endpoint-body {{
      padding: 20px;
    }}
    .endpoint-desc {{
      margin-bottom: 16px;
      font-size: 14px;
      color: var(--text);
    }}
    pre, code {{
      font-family: 'Fira Code', monospace;
    }}
    .code-wrapper {{
      position: relative;
      margin-top: 10px;
    }}
    pre {{
      background: var(--code-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 14px 16px;
      overflow-x: auto;
      font-size: 13px;
      color: #e2e8f0;
      line-height: 1.55;
    }}
    code {{
      background: rgba(148, 163, 184, 0.15);
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 12.5px;
      color: #f1f5f9;
    }}
    .copy-btn {{
      position: absolute;
      top: 8px;
      right: 8px;
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      padding: 4px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s ease;
    }}
    .copy-btn:hover {{
      background: rgba(255, 255, 255, 0.15);
      color: var(--text-bold);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 14px 0;
      font-size: 13.5px;
    }}
    th, td {{
      padding: 10px 12px;
      text-align: left;
      border-bottom: 1px solid var(--card-border);
    }}
    th {{
      color: var(--text-muted);
      font-weight: 600;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .tab-bar {{
      display: flex;
      gap: 6px;
      margin-bottom: 12px;
      border-bottom: 1px solid var(--card-border);
      padding-bottom: 8px;
    }}
    .tab-btn {{
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-muted);
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 13px;
      cursor: pointer;
      font-weight: 600;
      transition: all 0.15s ease;
    }}
    .tab-btn:hover {{
      color: var(--text);
    }}
    .tab-btn.active {{
      background: rgba(56, 189, 248, 0.15);
      color: var(--primary);
      border-color: rgba(56, 189, 248, 0.3);
    }}
    .tab-content {{
      display: none;
    }}
    .tab-content.active {{
      display: block;
    }}
    .alert {{
      padding: 12px 16px;
      border-radius: 8px;
      font-size: 13px;
      margin-top: 14px;
      display: flex;
      align-items: flex-start;
      gap: 10px;
    }}
    .alert-info {{
      background: rgba(56, 189, 248, 0.08);
      border: 1px solid rgba(56, 189, 248, 0.25);
      color: #bae6fd;
    }}
    .alert-warning {{
      background: rgba(245, 158, 11, 0.08);
      border: 1px solid rgba(245, 158, 11, 0.25);
      color: #fde68a;
    }}
    .workflow-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 14px;
      margin: 18px 0;
    }}
    .workflow-card {{
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 14px;
    }}
    .workflow-card h4 {{
      color: var(--text-bold);
      font-size: 14px;
      margin-bottom: 4px;
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    .workflow-card p {{
      font-size: 12.5px;
      color: var(--text-muted);
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="header-top">
        <div class="badges">
          <span class="badge">🚀 Gateway v1.0</span>
          <span class="badge agent">🤖 AI Agent Ready</span>
          <span class="badge">⚡ Instant Fulfillment</span>
        </div>
        <div class="quick-links">
          <a href="{openapi_url}" target="_blank" class="btn btn-primary">OpenAPI 3.1.0 JSON</a>
          <a href="https://t.me/{bot_user}" target="_blank" class="btn btn-outline">Open Bot @{bot_user}</a>
        </div>
      </div>
      <h1>{store_name} — Reseller & Developer API</h1>
      <p>Programmatic wholesale catalog synchronization, atomic wallet balance fulfillment, and instant digital credential delivery. Fully compatible with Reseller bots, e-commerce storefronts, and autonomous AI agents.</p>
      <nav class="toc">
        <a href="#getting-started">Getting Started</a>
        <a href="#authentication">Authentication</a>
        <a href="#ai-agent-guide">AI Agent & GPTs Quickstart</a>
        <a href="#endpoints">Endpoints Reference</a>
        <a href="#code-examples">Code Examples</a>
        <a href="#error-codes">Error Codes</a>
      </nav>
    </header>

    <!-- SECTION: GETTING STARTED -->
    <h2 id="getting-started">🚀 Getting Started</h2>
    <div class="card card-highlight">
      <div class="step">
        <div class="step-num">1</div>
        <div class="step-content">
          <h3>Generate Your Secret API Key</h3>
          <p>Open <a href="https://t.me/{bot_user}" target="_blank" style="color:var(--primary); font-weight:600;">@{bot_user}</a> in Telegram, go to <b>Account</b> &rarr; <b>Developer API</b>, and click <b>Generate Key</b>. By default, keys are not pre-generated for security. Once generated, keep your key secret!</p>
        </div>
      </div>
      <div class="step">
        <div class="step-num">2</div>
        <div class="step-content">
          <h3>Top Up Your Wallet Balance</h3>
          <p>All programmatic purchases atomically debit funds from your wallet balance. Standard accounts can use the API at regular retail rates; approved resellers automatically receive wholesale discounted pricing across all products.</p>
        </div>
      </div>
      <div class="step">
        <div class="step-num">3</div>
        <div class="step-content">
          <h3>Connect Your Bot or AI Agent</h3>
          <p>Pass your API key in the <code>X-API-Key</code> request header. For AI Agents (Custom GPTs, Claude, LangChain), simply import the OpenAPI 3.1.0 schema specification URL.</p>
        </div>
      </div>
    </div>

    <!-- SECTION: AUTHENTICATION -->
    <h2 id="authentication">🔑 Authentication & API Key Format</h2>
    <div class="card">
      <p>Every API request must authenticate using your secret API key. You can provide the key using either header:</p>
      
      <div class="code-wrapper">
        <button class="copy-btn" onclick="copySnippet(this)">Copy</button>
        <pre><code>X-API-Key: rkliveYOUR_API_KEY_HERE</code></pre>
      </div>

      <p style="margin-top: 10px;">Or using standard Bearer authentication:</p>
      <div class="code-wrapper">
        <button class="copy-btn" onclick="copySnippet(this)">Copy</button>
        <pre><code>Authorization: Bearer rkliveYOUR_API_KEY_HERE</code></pre>
      </div>

      <div class="alert alert-warning">
        <div>
          <b>Key Format Notice:</b> API keys begin with the prefix <code>rklive</code> immediately followed by 32 random alphanumeric characters (e.g. <code>rkliveHd6EYNrMsXeAy2CEZc1uoorAovsAA6Cc</code>). There are no hyphens or underscores. The string <code>rkliveYOUR_API_KEY_HERE</code> above is an example placeholder — replace it with the actual key you generated in the Telegram bot.
        </div>
      </div>

      <div class="alert alert-info" style="margin-top: 10px;">
        <div><b>Base URL:</b> <code>{api_base}</code></div>
      </div>
    </div>

    <!-- SECTION: AI AGENT QUICKSTART -->
    <h2 id="ai-agent-guide">🤖 Autonomous AI Agent & Custom GPTs Quickstart</h2>
    <div class="card card-agent">
      <p>This API provides full support for autonomous AI agents, ChatGPT Custom GPT Actions, Anthropic Claude Tool Use, LangChain OpenAPI Toolkit, CrewAI, AutoGen, and Cursor / AI IDE agents.</p>

      <div style="margin: 18px 0 10px;">
        <label style="font-size: 13px; font-weight: 600; color: var(--text-bold); display: block; margin-bottom: 6px;">Direct OpenAPI 3.1.0 Specification URL:</label>
        <div class="code-wrapper" style="margin-top: 0;">
          <button class="copy-btn" onclick="copySnippet(this)">Copy URL</button>
          <pre><code>{openapi_url}</code></pre>
        </div>
      </div>

      <h3 style="font-size: 15px; color: var(--text-bold); margin: 20px 0 10px;">Agent Procurement Workflow</h3>
      <div class="workflow-grid">
        <div class="workflow-card">
          <h4>1. Check Catalog</h4>
          <p>Call <code>GET /products</code> to inspect active products, live stock counts, and wholesale pricing.</p>
        </div>
        <div class="workflow-card">
          <h4>2. Verify Balance</h4>
          <p>Call <code>GET /me</code> to verify that wallet balance is greater than or equal to total price.</p>
        </div>
        <div class="workflow-card">
          <h4>3. Place Order</h4>
          <p>Call <code>POST /orders</code> with <code>product_id</code>, <code>quantity</code>, and a unique <code>custom_id</code> for safe idempotency.</p>
        </div>
        <div class="workflow-card">
          <h4>4. Return Credentials</h4>
          <p>Extract <code>credentials</code> from the 200 response and deliver directly to the customer.</p>
        </div>
      </div>

      <h3 style="font-size: 15px; color: var(--text-bold); margin: 20px 0 8px;">Recommended AI Agent System Prompt</h3>
      <div class="code-wrapper">
        <button class="copy-btn" onclick="copySnippet(this)">Copy Prompt</button>
        <pre><code>You are an autonomous digital goods procurement assistant integrated with the {store_name} Reseller API.
API Base: {api_base}
OpenAPI Specification: {openapi_url}

Rules for autonomous operation:
1. Before recommending or ordering, always fetch live stock and wholesale rates via GET /products.
2. Check user wallet balance via GET /me to ensure sufficient funds exist before purchasing.
3. To purchase, call POST /orders with product_id, quantity, and a unique custom_id (e.g. agent_order_&lt;timestamp_or_uuid&gt;).
4. If fulfillment is "delivered", immediately relay the delivered credentials to the buyer.
5. All requests must pass your API key in header "X-API-Key: &lt;your_key&gt;".</code></pre>
      </div>
    </div>

    <!-- SECTION: ENDPOINTS REFERENCE -->
    <h2 id="endpoints">📡 Endpoints Reference</h2>

    <!-- ENDPOINT 1: ME -->
    <div class="endpoint">
      <div class="endpoint-header">
        <span class="method get">GET</span>
        <span class="path">/api/v1/reseller/me</span>
      </div>
      <div class="endpoint-body">
        <p class="endpoint-desc">Inspect your account role (<code>Member</code> or <code>Reseller</code>), live wallet balance, currency, and API key metadata.</p>
        <p style="font-size: 13px; font-weight: 600; color: var(--text-bold); margin-bottom: 6px;">Sample Response (200 OK):</p>
        <div class="code-wrapper">
          <button class="copy-btn" onclick="copySnippet(this)">Copy</button>
          <pre><code>{{
  "success": true,
  "user": {{
    "user_id": 12,
    "tg_user_id": 100200300,
    "username": "reseller_pro",
    "name": "Alex Smith",
    "rank": "Reseller",
    "balance": 2450.0,
    "currency": "{currency}",
    "currency_symbol": "{symbol}",
    "total_spent": 12500.0
  }},
  "api_key": {{
    "prefix": "rklive••••••••A6Cc",
    "created_at": "2026-10-14T10:00:00Z",
    "last_used_at": "2026-10-14T12:30:00Z"
  }}
}}</code></pre>
        </div>
      </div>
    </div>

    <!-- ENDPOINT 2: PRODUCTS -->
    <div class="endpoint">
      <div class="endpoint-header">
        <span class="method get">GET</span>
        <span class="path">/api/v1/reseller/products</span>
      </div>
      <div class="endpoint-body">
        <p class="endpoint-desc">List all active store products with real-time stock units and wholesale reseller pricing.</p>
        <table>
          <thead><tr><th>Parameter</th><th>Type</th><th>Required</th><th>Description</th></tr></thead>
          <tbody>
            <tr><td><code>category_id</code></td><td>integer</td><td>No</td><td>Optional category filter ID</td></tr>
          </tbody>
        </table>
        <p style="font-size: 13px; font-weight: 600; color: var(--text-bold); margin: 12px 0 6px;">Sample Response (200 OK):</p>
        <div class="code-wrapper">
          <button class="copy-btn" onclick="copySnippet(this)">Copy</button>
          <pre><code>{{
  "success": true,
  "count": 2,
  "currency": "{currency}",
  "currency_symbol": "{symbol}",
  "products": [
    {{
      "id": 1,
      "title": "NordVPN 1 Month Private Account",
      "category_id": 1,
      "category_name": "VPN Accounts",
      "regular_price": 150.0,
      "reseller_price": 120.0,
      "has_discount": true,
      "discount_percent": 20,
      "stock": 14,
      "in_stock": true,
      "delivery_type": "instant",
      "duration": "1 Month",
      "icon": "🛡️"
    }}
  ]
}}</code></pre>
        </div>
      </div>
    </div>

    <!-- ENDPOINT 3: SINGLE PRODUCT -->
    <div class="endpoint">
      <div class="endpoint-header">
        <span class="method get">GET</span>
        <span class="path">/api/v1/reseller/products/{{product_id}}</span>
      </div>
      <div class="endpoint-body">
        <p class="endpoint-desc">Inspect a single product's real-time inventory and pricing before placing an order.</p>
        <table>
          <thead><tr><th>Path Parameter</th><th>Type</th><th>Required</th><th>Description</th></tr></thead>
          <tbody>
            <tr><td><code>product_id</code></td><td>integer</td><td>Yes</td><td>Target product ID</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ENDPOINT 4: CREATE ORDER -->
    <div class="endpoint">
      <div class="endpoint-header">
        <span class="method post">POST</span>
        <span class="path">/api/v1/reseller/orders</span>
      </div>
      <div class="endpoint-body">
        <p class="endpoint-desc">Instantly purchase a product. Balance is debited atomically. For instant-delivery items, account credentials or license keys are immediately returned in the response!</p>
        <table>
          <thead><tr><th>Body Field</th><th>Type</th><th>Required</th><th>Description</th></tr></thead>
          <tbody>
            <tr><td><code>product_id</code></td><td>integer</td><td>Yes</td><td>ID of product to purchase</td></tr>
            <tr><td><code>quantity</code></td><td>integer</td><td>No (default 1)</td><td>Quantity to buy (1-100)</td></tr>
            <tr><td><code>custom_id</code></td><td>string</td><td>Yes*</td><td>Unique order reference (1-64 chars) for safe retries and idempotency. *Alternatively supply Idempotency-Key header.</td></tr>
          </tbody>
        </table>
        
        <p style="font-size: 13px; font-weight: 600; color: var(--text-bold); margin: 12px 0 6px;">Request Body Example:</p>
        <div class="code-wrapper">
          <button class="copy-btn" onclick="copySnippet(this)">Copy</button>
          <pre><code>{{
  "product_id": 1,
  "quantity": 1,
  "custom_id": "bot_order_991823"
}}</code></pre>
        </div>

        <p style="font-size: 13px; font-weight: 600; color: var(--text-bold); margin: 16px 0 6px;">Sample Response (200 OK — Instant Delivery):</p>
        <div class="code-wrapper">
          <button class="copy-btn" onclick="copySnippet(this)">Copy</button>
          <pre><code>{{
  "success": true,
  "order_id": 492,
  "custom_id": "bot_order_991823",
  "product_id": 1,
  "product_title": "NordVPN 1 Month Private Account",
  "quantity": 1,
  "unit_price": 120.0,
  "total_price": 120.0,
  "currency": "{currency}",
  "currency_symbol": "{symbol}",
  "balance_after": 2330.0,
  "fulfillment": "delivered",
  "credentials": "email: user@example.com\\npassword: SuperSecretPass123",
  "created_at": "2026-10-14T21:45:00Z",
  "message": "Order delivered instantly."
}}</code></pre>
        </div>
      </div>
    </div>

    <!-- ENDPOINT 5: LIST ORDERS -->
    <div class="endpoint">
      <div class="endpoint-header">
        <span class="method get">GET</span>
        <span class="path">/api/v1/reseller/orders</span>
      </div>
      <div class="endpoint-body">
        <p class="endpoint-desc">List recent orders placed by your account with pagination.</p>
        <table>
          <thead><tr><th>Parameter</th><th>Type</th><th>Default</th><th>Description</th></tr></thead>
          <tbody>
            <tr><td><code>limit</code></td><td>integer</td><td>20</td><td>Number of records (1-100)</td></tr>
            <tr><td><code>offset</code></td><td>integer</td><td>0</td><td>Pagination offset</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ENDPOINT 6: GET ORDER -->
    <div class="endpoint">
      <div class="endpoint-header">
        <span class="method get">GET</span>
        <span class="path">/api/v1/reseller/orders/{{order_id}}</span>
      </div>
      <div class="endpoint-body">
        <p class="endpoint-desc">Retrieve order status and re-fetch credentials for any order placed by your account.</p>
        <table>
          <thead><tr><th>Path Parameter</th><th>Type</th><th>Required</th><th>Description</th></tr></thead>
          <tbody>
            <tr><td><code>order_id</code></td><td>integer</td><td>Yes</td><td>Order ID to inspect</td></tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- SECTION: CODE EXAMPLES -->
    <h2 id="code-examples">💻 Code Integration Examples</h2>
    <div class="card">
      <div class="tab-bar">
        <button class="tab-btn active" onclick="switchTab(this, 'tab-python')">Python</button>
        <button class="tab-btn" onclick="switchTab(this, 'tab-node')">Node.js</button>
        <button class="tab-btn" onclick="switchTab(this, 'tab-curl')">cURL</button>
      </div>

      <!-- PYTHON TAB -->
      <div id="tab-python" class="tab-content active">
        <div class="code-wrapper">
          <button class="copy-btn" onclick="copySnippet(this)">Copy Python</button>
          <pre><code>import requests

API_KEY = "rkliveYOUR_API_KEY_HERE"  # Replace with your actual key from Telegram bot
BASE_URL = "{api_base}"
HEADERS = {{"X-API-Key": API_KEY, "Content-Type": "application/json"}}

# 1. Check your balance
me = requests.get(f"{{BASE_URL}}/me", headers=HEADERS).json()
print("Balance:", me["user"]["balance"], me["user"]["currency_symbol"])

# 2. Browse products
catalog = requests.get(f"{{BASE_URL}}/products", headers=HEADERS).json()
for p in catalog["products"]:
    print(f"[#{{p['id']}}] {{p['title']}} - Rate: {{p['reseller_price']}} | Stock: {{p['stock']}}")

# 3. Buy a product with instant delivery
order_payload = {{
    "product_id": 1,
    "quantity": 1,
    "custom_id": "merchant_order_123"
}}
order = requests.post(f"{{BASE_URL}}/orders", json=order_payload, headers=HEADERS).json()

if order.get("success"):
    print("Order Fulfilled! ID:", order["order_id"])
    print("Delivered Credentials:")
    print(order["credentials"])
else:
    print("Order failed:", order.get("detail"))
</code></pre>
        </div>
      </div>

      <!-- NODE.JS TAB -->
      <div id="tab-node" class="tab-content">
        <div class="code-wrapper">
          <button class="copy-btn" onclick="copySnippet(this)">Copy JavaScript</button>
          <pre><code>const API_KEY = "rkliveYOUR_API_KEY_HERE";  // Replace with your actual key
const BASE_URL = "{api_base}";

async function purchaseProduct(productId, customId) {{
  const response = await fetch(`${{BASE_URL}}/orders`, {{
    method: "POST",
    headers: {{
      "X-API-Key": API_KEY,
      "Content-Type": "application/json"
    }},
    body: JSON.stringify({{
      product_id: productId,
      quantity: 1,
      custom_id: customId
    }})
  }});

  const data = await response.json();
  if (response.ok && data.success) {{
    console.log("Credentials delivered:", data.credentials);
    return data;
  }} else {{
    throw new Error(data.detail || "Purchase failed");
  }}
}}
</code></pre>
        </div>
      </div>

      <!-- CURL TAB -->
      <div id="tab-curl" class="tab-content">
        <div class="code-wrapper">
          <button class="copy-btn" onclick="copySnippet(this)">Copy cURL</button>
          <pre><code># 1. Check balance
curl -H "X-API-Key: rkliveYOUR_API_KEY_HERE" {api_base}/me

# 2. List products
curl -H "X-API-Key: rkliveYOUR_API_KEY_HERE" {api_base}/products

# 3. Purchase product (instant delivery)
curl -X POST {api_base}/orders \\
  -H "X-API-Key: rkliveYOUR_API_KEY_HERE" \\
  -H "Content-Type: application/json" \\
  -d '{{"product_id": 1, "quantity": 1, "custom_id": "test_order_01"}}'
</code></pre>
        </div>
      </div>
    </div>

    <!-- SECTION: ERROR CODES -->
    <h2 id="error-codes">⚠️ HTTP Error Codes Reference</h2>
    <div class="card">
      <table>
        <thead><tr><th>Code</th><th>Name</th><th>Meaning</th></tr></thead>
        <tbody>
          <tr><td><code>200 OK</code></td><td>Success</td><td>Request completed successfully.</td></tr>
          <tr><td><code>400 Bad Request</code></td><td>Action Failed</td><td>Insufficient balance or item out of stock. Inspect the <code>detail</code> message.</td></tr>
          <tr><td><code>401 Unauthorized</code></td><td>Invalid Key</td><td>API key is missing, malformed, or revoked.</td></tr>
          <tr><td><code>403 Forbidden</code></td><td>Restricted</td><td>Account is suspended or access is blocked.</td></tr>
          <tr><td><code>404 Not Found</code></td><td>Not Found</td><td>Product ID or Order ID does not exist.</td></tr>
          <tr><td><code>422 Unprocessable</code></td><td>Validation Error</td><td>Missing <code>custom_id</code> or payload constraints violated.</td></tr>
          <tr><td><code>429 Too Many Requests</code></td><td>Rate Limit</td><td>Rate limit exceeded. Check <code>Retry-After</code> header.</td></tr>
          <tr><td><code>503 Service Unavailable</code></td><td>Store Paused</td><td>Store maintenance in progress.</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <script>
    function copySnippet(button) {{
      const wrapper = button.closest('.code-wrapper');
      const code = wrapper.querySelector('pre code') || wrapper.querySelector('pre');
      if (!code) return;
      navigator.clipboard.writeText(code.innerText.trim()).then(() => {{
        const originalText = button.innerText;
        button.innerText = 'Copied!';
        button.style.color = '#34d399';
        setTimeout(() => {{
          button.innerText = originalText;
          button.style.color = '';
        }}, 2000);
      }}).catch(() => {{
        button.innerText = 'Error';
      }});
    }}

    function switchTab(button, tabId) {{
      const container = button.closest('.card');
      container.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
      container.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
      button.classList.add('active');
      const target = document.getElementById(tabId);
      if (target) target.classList.add('active');
    }}
  </script>
</body>
</html>
"""


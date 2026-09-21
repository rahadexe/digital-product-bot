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

    rank = (reseller.get("rank") or "").strip().lower()
    if rank != "reseller":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only authorized Resellers can access this API.",
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
            "name": f"{reseller.get('first_name') or ''} {reseller.get('last_name') or ''}".strip() or "Reseller",
            "rank": reseller.get("rank") or "Reseller",
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

    products = await services.reseller.get_reseller_products(category_id=category_id)
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

    product = await services.reseller.get_reseller_product(product_id)
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
    Purchase a product programmatically at discounted reseller pricing.
    Deducts balance atomically from reseller wallet and immediately returns delivered credentials in response.
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
        require_reseller=True,
        reseller_key_id=reseller['key_id'],
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


@router.get("/docs", response_class=HTMLResponse, include_in_schema=False)
async def reseller_documentation_page(request: Request, services: ServicesDep):
    """Interactive, developer-friendly Reseller API documentation page with code examples."""
    settings_vals = await services.settings.values()
    store_name = escape(settings_vals.get("store_name", "Premium Store"))
    currency = escape(settings_vals.get("currency", "BDT"))
    symbol = escape(settings_vals.get("currency_symbol", "৳"))
    bot_user = escape(await services.notifier.bot_username(), quote=True)
    base_url = escape(str(request.base_url).rstrip("/"), quote=True)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{store_name} - Reseller API Documentation</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600&family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #0d1117;
      --card-bg: #161b22;
      --card-border: #30363d;
      --text: #c9d1d9;
      --text-bold: #f0f6fc;
      --text-muted: #8b949e;
      --primary: #58a6ff;
      --accent: #2ea043;
      --warning: #d29922;
      --danger: #f85149;
      --code-bg: #090d12;
      --tag-get: #388bfd33;
      --tag-get-text: #58a6ff;
      --tag-post: #2ea04333;
      --tag-post-text: #3fb950;
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
      max-width: 960px;
      margin: 0 auto;
    }}
    header {{
      padding: 40px 0 24px;
      border-bottom: 1px solid var(--card-border);
      margin-bottom: 32px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
      background: rgba(88, 166, 255, 0.15);
      color: var(--primary);
      border: 1px solid rgba(88, 166, 255, 0.3);
      margin-bottom: 12px;
    }}
    h1 {{
      font-size: 28px;
      font-weight: 800;
      color: var(--text-bold);
      margin-bottom: 8px;
    }}
    header p {{
      color: var(--text-muted);
      font-size: 15px;
    }}
    h2 {{
      font-size: 20px;
      font-weight: 700;
      color: var(--text-bold);
      margin: 36px 0 16px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 24px;
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
      border: 1px solid rgba(88, 166, 255, 0.4);
    }}
    .method.post {{
      background: var(--tag-post);
      color: var(--tag-post-text);
      border: 1px solid rgba(46, 160, 67, 0.4);
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
    }}
    pre, code {{
      font-family: 'Fira Code', monospace;
    }}
    pre {{
      background: var(--code-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 14px 16px;
      overflow-x: auto;
      font-size: 13px;
      margin-top: 10px;
      color: #e6edf3;
    }}
    code {{
      background: rgba(110, 118, 129, 0.2);
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 12.5px;
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
    }}
    .tab-container {{
      margin-top: 14px;
    }}
    .tab-buttons {{
      display: flex;
      gap: 6px;
      margin-bottom: 8px;
    }}
    .tab-btn {{
      background: transparent;
      border: 1px solid var(--card-border);
      color: var(--text-muted);
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 12px;
      cursor: pointer;
      font-weight: 600;
    }}
    .tab-btn.active {{
      background: var(--primary);
      color: #0d1117;
      border-color: var(--primary);
    }}
    .step {{
      display: flex;
      gap: 16px;
      margin-bottom: 16px;
    }}
    .step-num {{
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: var(--primary);
      color: #0d1117;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 14px;
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
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="badge">🚀 Developer Gateway</div>
      <h1>{store_name} — Reseller API Docs</h1>
      <p>Connect your Telegram bot, website, or store directly to our inventory. Buy at exclusive reseller rates with instant automated delivery.</p>
    </header>

    <h2>🔑 Getting Started</h2>
    <div class="card">
      <div class="step">
        <div class="step-num">1</div>
        <div class="step-content">
          <h3>Become an Authorized Reseller</h3>
          <p>Contact store support or deposit the required minimum balance. Your account role will be set to <code>Reseller</code>.</p>
        </div>
      </div>
      <div class="step">
        <div class="step-num">2</div>
        <div class="step-content">
          <h3>Generate Your API Key</h3>
          <p>Open <a href="https://t.me/{bot_user}" target="_blank" style="color:var(--primary);">@{bot_user}</a>, type <code>/reseller</code> or tap <b>Apply as a Reseller</b> &rarr; <b>Generate API Key</b>. Keep this key safe!</p>
        </div>
      </div>
      <div class="step">
        <div class="step-num">3</div>
        <div class="step-content">
          <h3>Top Up Your Wallet Balance</h3>
          <p>Every purchase via the API deducts funds from your wallet balance at your discounted reseller rate. Deposit via bKash, Nagad, Binance Pay, or USDT inside the bot.</p>
        </div>
      </div>
    </div>

    <h2>🛡️ Authentication</h2>
    <div class="card">
      <p>Authenticate every request by passing your secret API Key in the headers using either <code>X-API-Key</code> or <code>Authorization: Bearer</code>:</p>
      <pre><code>X-API-Key: rk_live_your_secret_api_key_here</code></pre>
      <p style="margin-top: 8px;">Or standard bearer token:</p>
      <pre><code>Authorization: Bearer rk_live_your_secret_api_key_here</code></pre>
      <p style="margin-top: 12px; color: var(--text-muted); font-size: 13px;"><b>Base URL:</b> <code>{base_url}/api/v1/reseller</code></p>
    </div>

    <h2>📦 API Endpoints</h2>

    <!-- ENDPOINT 1: ME -->
    <div class="endpoint">
      <div class="endpoint-header">
        <span class="method get">GET</span>
        <span class="path">/api/v1/reseller/me</span>
      </div>
      <div class="endpoint-body">
        <p class="endpoint-desc">Check your reseller account profile, live wallet balance, and total order count.</p>
        <p><b>Sample Response (200 OK):</b></p>
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
    "prefix": "rk_live_9b4e...3a1f",
    "created_at": "2026-09-20T12:00:00Z",
    "last_used_at": "2026-09-20T15:30:00Z"
  }}
}}</code></pre>
      </div>
    </div>

    <!-- ENDPOINT 2: PRODUCTS -->
    <div class="endpoint">
      <div class="endpoint-header">
        <span class="method get">GET</span>
        <span class="path">/api/v1/reseller/products</span>
      </div>
      <div class="endpoint-body">
        <p class="endpoint-desc">Fetch the complete catalog of active products with real-time stock units and wholesale reseller pricing.</p>
        <table>
          <thead><tr><th>Param</th><th>Type</th><th>Description</th></tr></thead>
          <tbody>
            <tr><td><code>category_id</code></td><td>integer</td><td>Optional category filter ID</td></tr>
          </tbody>
        </table>
        <p><b>Sample Response (200 OK):</b></p>
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

    <!-- ENDPOINT 3: SINGLE PRODUCT -->
    <div class="endpoint">
      <div class="endpoint-header">
        <span class="method get">GET</span>
        <span class="path">/api/v1/reseller/products/{{product_id}}</span>
      </div>
      <div class="endpoint-body">
        <p class="endpoint-desc">Inspect a single product's real-time inventory and pricing before placing an order.</p>
      </div>
    </div>

    <!-- ENDPOINT 4: CREATE ORDER -->
    <div class="endpoint">
      <div class="endpoint-header">
        <span class="method post">POST</span>
        <span class="path">/api/v1/reseller/orders</span>
      </div>
      <div class="endpoint-body">
        <p class="endpoint-desc">Instantly purchase a product at your wholesale reseller price. For instant-delivery products, account credentials or license keys are returned directly in the response!</p>
        <table>
          <thead><tr><th>Body Field</th><th>Type</th><th>Required</th><th>Description</th></tr></thead>
          <tbody>
            <tr><td><code>product_id</code></td><td>integer</td><td>Yes</td><td>ID of the product to purchase</td></tr>
            <tr><td><code>quantity</code></td><td>integer</td><td>No (default 1)</td><td>Number of units to buy</td></tr>
            <tr><td><code>custom_id</code></td><td>string</td><td>Yes*</td><td>Unique order reference; reuse on retry. *Alternatively supply the Idempotency-Key header.</td></tr>
          </tbody>
        </table>
        <p><b>Request Body Example:</b></p>
        <pre><code>{{
  "product_id": 1,
  "quantity": 1,
  "custom_id": "bot_order_991823"
}}</code></pre>
        <p style="margin-top:14px;"><b>Sample Response (200 OK — Instant Delivery):</b></p>
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
  "created_at": "2026-09-20T21:45:00Z",
  "message": "Order delivered instantly."
}}</code></pre>
      </div>
    </div>

    <!-- ENDPOINT 5: GET ORDER -->
    <div class="endpoint">
      <div class="endpoint-header">
        <span class="method get">GET</span>
        <span class="path">/api/v1/reseller/orders/{{order_id}}</span>
      </div>
      <div class="endpoint-body">
        <p class="endpoint-desc">Retrieve order status and re-fetch credentials for any order placed by your account.</p>
      </div>
    </div>

    <h2>💻 Integration Code Examples</h2>

    <!-- PYTHON EXAMPLE -->
    <div class="card">
      <h3>Python (Requests / Telegram Bot Integration)</h3>
      <pre><code>import requests

API_KEY = "rk_live_your_key_here"
BASE_URL = "{base_url}/api/v1/reseller"
HEADERS = {{"X-API-Key": API_KEY, "Content-Type": "application/json"}}

# 1. Check your balance
res = requests.get(f"{{BASE_URL}}/me", headers=HEADERS).json()
print("My Balance:", res["user"]["balance"], res["user"]["currency_symbol"])

# 2. Get available stock & reseller prices
catalog = requests.get(f"{{BASE_URL}}/products", headers=HEADERS).json()
for p in catalog["products"]:
    print(f"[#{{p['id']}}] {{p['title']}} - Rate: {{p['reseller_price']}} | Stock: {{p['stock']}}")

# 3. Buy a product with instant delivery
order_payload = {{
    "product_id": 1,
    "quantity": 1,
    "custom_id": "my_tg_bot_order_123"
}}
order = requests.post(f"{{BASE_URL}}/orders", json=order_payload, headers=HEADERS).json()

if order.get("success"):
    print("Order Placed! ID:", order["order_id"])
    print("Delivered Credentials:")
    print(order["credentials"])
else:
    print("Purchase failed:", order.get("detail"))
</code></pre>
    </div>

    <!-- NODE.JS EXAMPLE -->
    <div class="card">
      <h3>Node.js / JavaScript (Fetch / Axios)</h3>
      <pre><code>const API_KEY = "rk_live_your_key_here";
const BASE_URL = "{base_url}/api/v1/reseller";

async function buyProduct(productId, customId) {{
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
    console.log("Credentials:", data.credentials);
    return data;
  }} else {{
    throw new Error(data.detail || "Purchase failed");
  }}
}}
</code></pre>
    </div>

    <!-- CURL EXAMPLE -->
    <div class="card">
      <h3>cURL (Terminal / Command Line)</h3>
      <pre><code># Check balance
curl -H "X-API-Key: rk_live_your_key_here" {base_url}/api/v1/reseller/me

# List products
curl -H "X-API-Key: rk_live_your_key_here" {base_url}/api/v1/reseller/products

# Purchase product
curl -X POST {base_url}/api/v1/reseller/orders \\
  -H "X-API-Key: rk_live_your_key_here" \\
  -H "Content-Type: application/json" \\
  -d '{{"product_id": 1, "quantity": 1, "custom_id": "curl_test_01"}}'
</code></pre>
    </div>

    <h2>⚠️ HTTP Error Codes</h2>
    <div class="card">
      <table>
        <thead><tr><th>Code</th><th>Name</th><th>Meaning</th></tr></thead>
        <tbody>
          <tr><td><code>200 OK</code></td><td>Success</td><td>Request completed successfully.</td></tr>
          <tr><td><code>401 Unauthorized</code></td><td>Invalid Key</td><td>API Key is missing, malformed, or revoked.</td></tr>
          <tr><td><code>403 Forbidden</code></td><td>Not a Reseller</td><td>Account is not registered with <code>Reseller</code> rank or is banned.</td></tr>
          <tr><td><code>400 Bad Request</code></td><td>Action Failed</td><td>Insufficient balance or item out of stock. Check <code>detail</code> message.</td></tr>
          <tr><td><code>404 Not Found</code></td><td>Not Found</td><td>Product or order ID does not exist.</td></tr>
          <tr><td><code>503 Service Unavailable</code></td><td>Store Paused</td><td>Store maintenance in progress.</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.admin.schemas import ProductPayload, ProductUpdatePayload
from app.bot.handlers.shop import (
    execute_legacy_purchase,
    execute_quantity_purchase,
    handle_buy_now_by_text,
)
from app.db.migrations import MIGRATIONS_DIR
from app.services.catalog import PRODUCT_FIELDS
from app.services.purchases import _receipt_fields


def test_customer_input_schemas():
    # Test ProductPayload with customer input enabled
    p = ProductPayload(
        title="Gemini 1 Year Invite",
        price=150.0,
        requires_customer_input=1,
        customer_input_prompt="Enter your Gmail address",
    )
    assert p.requires_customer_input == 1
    assert p.customer_input_prompt == "Enter your Gmail address"

    # Test ProductUpdatePayload
    u = ProductUpdatePayload(
        requires_customer_input=0,
        customer_input_prompt="",
    )
    assert u.requires_customer_input == 0
    assert u.customer_input_prompt == ""


def test_catalog_fields_and_receipt():
    assert "requires_customer_input" in PRODUCT_FIELDS
    assert "customer_input_prompt" in PRODUCT_FIELDS

    row = {
        "id": 101,
        "product_title": "Gemini 1 Year",
        "price": 10.0,
        "delivered_item": "",
        "fulfillment": "waiting",
        "customer_input": "user@gmail.com",
        "created_at": None,
    }
    receipt = _receipt_fields(row, balance=50.0)
    assert receipt["customer_input"] == "user@gmail.com"
    assert receipt["order_id"] == 101


def test_migration_0052_exists():
    mig = MIGRATIONS_DIR / "0052_product_customer_input.sql"
    assert mig.exists(), "Migration 0052 must exist"
    content = mig.read_text(encoding="utf-8")
    assert "requires_customer_input" in content
    assert "customer_input_prompt" in content
    assert "customer_input" in content


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["quantity", "legacy", "text"])
async def test_customer_input_cancel_returns_to_registered_product_route(entry):
    services = SimpleNamespace(
        catalog=SimpleNamespace(product=AsyncMock(return_value={
            "id": 42, "is_active": 1, "requires_customer_input": True,
        })),
        users=SimpleNamespace(get_language=AsyncMock(return_value="en")),
        purchases=SimpleNamespace(purchase=AsyncMock()),
    )
    state = SimpleNamespace(
        clear=AsyncMock(), set_state=AsyncMock(), update_data=AsyncMock(),
        get_data=AsyncMock(return_value={"active_product_id": 42}),
    )
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=123), answer=AsyncMock(), edit_text=AsyncMock(),
    )
    query = SimpleNamespace(
        data="buy_qty_42_1_testtoken" if entry == "quantity" else "buy_42_" + "a" * 32,
        from_user=message.from_user, message=message, answer=AsyncMock(),
    )
    if entry == "text":
        await handle_buy_now_by_text(message, state, services)
        markup = message.answer.await_args.kwargs["reply_markup"]
    else:
        handler = execute_quantity_purchase if entry == "quantity" else execute_legacy_purchase
        await handler(query, state, services)
        markup = message.edit_text.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].callback_data == "prod_42"
    services.purchases.purchase.assert_not_awaited()

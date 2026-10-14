import pytest
from app.api.admin.schemas import ProductPayload, ProductUpdatePayload
from app.services.catalog import PRODUCT_FIELDS
from app.services.purchases import _receipt_fields
from app.db.migrations import MIGRATIONS_DIR


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

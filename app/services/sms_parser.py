"""Parser for Bangladeshi MFS (bKash, Nagad, Rocket, Upay) payment SMS statements."""

from __future__ import annotations

import re
from typing import Any


def clean_amount(val: str) -> float:
    """Strip commas and whitespace, convert to float."""
    cleaned = val.replace(",", "").strip()
    return float(cleaned)


def parse_mfs_sms(raw_text: str, sender_hint: str = "") -> dict[str, Any] | None:
    """Parse payment confirmation SMS from bKash, Nagad, Rocket, or Upay.

    Returns dict with keys:
        - provider: str ('bKash', 'Nagad', 'Rocket', 'Upay')
        - transaction_id: str
        - amount: float
        - sender_number: str
        - raw_message: str
    or None if the message cannot be identified as an incoming payment receipt.
    """
    if not raw_text or not isinstance(raw_text, str):
        return None

    text = raw_text.strip()
    hint = (sender_hint or "").strip().lower()

    # Determine provider from sender header or text content
    provider = "bKash"
    if "nagad" in hint or "nagad" in text.lower():
        provider = "Nagad"
    elif "rocket" in hint or "16216" in hint or "dbbl" in hint or "rocket" in text.lower():
        provider = "Rocket"
    elif "upay" in hint or "upay" in text.lower():
        provider = "Upay"
    elif "bkash" in hint or "bkash" in text.lower():
        provider = "bKash"

    # 1. TrxID extraction
    # Common variants: TrxID 9ABC123456, TxnID: 7XYZ987654, TxnId: 1234567890, Trx ID: ABC123XYZ4
    tx_match = re.search(
        r"(?:trx\s*id|tx\s*n\s*id|transaction\s*id)[\s:#=]*([A-Za-z0-9]{6,25})",
        text,
        re.IGNORECASE,
    )
    if not tx_match:
        return None
    transaction_id = tx_match.group(1).strip()

    # 2. Amount extraction
    # Common variants:
    # bKash: "received Tk 500.00" / "received deposit of Tk 1,000.00" / "Cash In Tk 500.00"
    # Nagad: "Amount: Tk 300.00" / "Amount: Tk. 300"
    # Rocket: "Tk 200.00 received"
    amount = 0.0

    # Pattern A: Nagad / Upay explicit "Amount: Tk 300.00"
    amount_match_a = re.search(
        r"amount[\s:#=]*(?:tk|tk\.|bdt)?\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        text,
        re.IGNORECASE,
    )
    # Pattern B: bKash "received (deposit of )?Tk 500.00" or "Cash In Tk 500.00"
    amount_match_b = re.search(
        r"(?:received(?:\s+deposit\s+of)?|cash\s*in)\s+(?:tk|tk\.|bdt)?\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        text,
        re.IGNORECASE,
    )
    # Pattern C: Rocket "Tk 200.00 received"
    amount_match_c = re.search(
        r"(?:tk|tk\.|bdt)?\s*([0-9,]+(?:\.[0-9]{1,2})?)\s+received",
        text,
        re.IGNORECASE,
    )
    # Pattern D: General fallback "(Tk|Tk.|BDT) 500.00"
    amount_match_d = re.search(
        r"(?:tk|tk\.|bdt)\s*([0-9,]+(?:\.[0-9]{1,2})?)",
        text,
        re.IGNORECASE,
    )

    if amount_match_a:
        try:
            amount = clean_amount(amount_match_a.group(1))
        except (ValueError, TypeError):
            amount = 0.0
    elif amount_match_b:
        try:
            amount = clean_amount(amount_match_b.group(1))
        except (ValueError, TypeError):
            amount = 0.0
    elif amount_match_c:
        try:
            amount = clean_amount(amount_match_c.group(1))
        except (ValueError, TypeError):
            amount = 0.0
    elif amount_match_d:
        try:
            amount = clean_amount(amount_match_d.group(1))
        except (ValueError, TypeError):
            amount = 0.0

    if amount <= 0:
        return None

    # 3. Sender number extraction (optional)
    sender_number = ""
    sender_match = re.search(
        r"(?:from|sender[:\s]*)\s*(\+?880[0-9]{8,10}|01[3-9][0-9]{8})",
        text,
        re.IGNORECASE,
    )
    if sender_match:
        sender_number = sender_match.group(1).strip()

    return {
        "provider": provider,
        "transaction_id": transaction_id,
        "amount": amount,
        "sender_number": sender_number,
        "raw_message": text,
    }

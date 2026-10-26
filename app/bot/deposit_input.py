"""Strict money parsing with human-friendly digits, grouping and currency labels."""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal

_INTEGER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]{1,2}(?:,[0-9]{2})+,[0-9]{3}|[0-9]+)"
_NUMBER = rf"{_INTEGER}(?:\.[0-9]{{1,2}})?"
_PATTERNS = {
    is_binance: re.compile(
        rf"(?:{unit}\s*)?(?P<amount>{_NUMBER})(?:\s*{unit})?",
        re.IGNORECASE,
    )
    for is_binance, unit in (
        (False, r"(?:৳|BDT|Tk\.?|Taka|টাকা)"),
        (True, r"(?:\$|USD|USDT)"),
    )
}


def parse_deposit_amount(text: str, *, is_binance: bool = False) -> Decimal:
    """Accept one positive amount, never extract digits from arbitrary text.

    Decimal digits include Bengali and Arabic keyboards. Currency labels must
    match the selected method; no currency conversion is inferred from input.
    """
    error = "Enter a valid amount, e.g. 50."
    if not isinstance(text, str) or len(text) > 128:
        raise ValueError(error)
    normalised = unicodedata.normalize("NFKC", text)
    normalised = "".join(
        str(unicodedata.decimal(char)) if unicodedata.category(char) == "Nd" else char
        for char in normalised
        if unicodedata.category(char) != "Cf"
    ).strip().replace("٬", ",").replace("٫", ".")
    match = _PATTERNS[is_binance].fullmatch(normalised)
    if not match:
        raise ValueError(error)
    amount = Decimal(match["amount"].replace(",", ""))
    if not amount.is_finite() or amount <= 0:
        raise ValueError(error)
    return amount


def payment_instruction_note(instructions: str) -> str:
    """Return administrator-authored payment instructions without rewriting them."""
    return instructions.strip()

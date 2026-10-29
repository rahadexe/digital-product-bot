"""Short, escaped customer notifications shared by payment and order services."""

from html import escape

from app.bot.formatting import format_dual_price
from app.core.identifiers import format_deposit_id, format_order_id


def wallet_updated(amount: float, balance: float, symbol: str, deposit_id: int | None = None) -> str:
    added = format_dual_price(amount, symbol=symbol, show_usd=False, lang="en")
    total = format_dual_price(balance, symbol=symbol, show_usd=False, lang="en")
    return (
        "💰 <b>Balance Updated</b>\n\n"
        f"Added: <code>+{added}</code>\n"
        f"Current Balance: <code>{total}</code>"
    )


def order_refunded(order_id: int, title: str, amount: float, symbol: str) -> str:
    value = format_dual_price(amount, symbol=symbol, show_usd=False, lang="en")
    return (
        "🔄 <b>Order Refunded</b>\n\n"
        f"Product: <b>{escape(title)}</b>\n"
        f"Order ID: <code>{format_order_id(order_id)}</code>\n"
        f"Refunded: <code>{value}</code> returned to your balance."
    )

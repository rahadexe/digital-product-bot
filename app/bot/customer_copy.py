"""Short, escaped customer notifications shared by payment and order services."""

from html import escape

from app.bot.formatting import format_dual_price
from app.core.identifiers import format_deposit_id, format_order_id


def wallet_updated(amount: float, balance: float, symbol: str, deposit_id: int) -> str:
    added = format_dual_price(amount, symbol=symbol, show_usd=False, lang="en")
    total = format_dual_price(balance, symbol=symbol, show_usd=False, lang="en")
    return (
        "<b>Wallet updated</b>\n"
        f"<blockquote>Added: <code>{added}</code>\n"
        f"Balance: <code>{total}</code>\n"
        f"Ref: <code>{format_deposit_id(deposit_id)}</code></blockquote>"
    )


def order_refunded(order_id: int, title: str, amount: float, symbol: str) -> str:
    value = format_dual_price(amount, symbol=symbol, show_usd=False, lang="en")
    return (
        f"<b>Refunded · {format_order_id(order_id)}</b>\n"
        f"<blockquote><b>{escape(title)}</b>\n"
        f"<code>{value}</code> returned to your wallet.</blockquote>"
    )

"""Short, escaped customer notifications shared by payment and order services."""

from html import escape

from app.bot.formatting import format_dual_price
from app.core.identifiers import format_deposit_id, format_order_id


def wallet_updated(amount: float, balance: float, symbol: str, deposit_id: int | None = None,
                   *, currency: str = "USD", usd_rate: float | None = None) -> str:
    added = format_dual_price(amount, currency=currency, usd_rate=usd_rate)
    total = format_dual_price(balance, currency=currency, usd_rate=usd_rate)
    return (
        "💰 <b>Balance Updated</b>\n\n"
        f"Added: <code>+{added}</code>\n"
        f"Current Balance: <code>{total}</code>"
    )


def order_refunded(order_id: int, title: str, amount: float, symbol: str,
                   *, currency: str = "USD", usd_rate: float | None = None) -> str:
    value = format_dual_price(amount, currency=currency, usd_rate=usd_rate)
    return (
        "🔄 <b>Order Refunded</b>\n\n"
        f"Product: <b>{escape(title)}</b>\n"
        f"Order ID: <code>{format_order_id(order_id)}</code>\n"
        f"Refunded: <code>{value}</code> returned to your balance."
    )


def payment_summary(amount: float, pay_amount: float, *, is_binance: bool,
                    currency: str, usd_rate: float, paid: bool = False) -> str:
    """The payment rail determines what to send; preference determines wallet display."""
    payment = f"{pay_amount:g} USDT" if is_binance else f"{pay_amount:g} ৳"
    lines = [f"{'Paid' if paid else 'Send'}: <code>{payment}</code>"]
    if is_binance or currency == "USD":
        credit = format_dual_price(amount, currency=currency, usd_rate=usd_rate)
        lines.append(f"{'Added' if paid else 'Adds to balance'}: <code>{credit}</code>")
    return "\n".join(lines)

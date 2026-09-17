import math


def money(value: float, *, positive: bool = False) -> float:
    value = float(value)
    if not math.isfinite(value) or abs(value) > 1_000_000_000:
        raise ValueError("Amount must be finite and within the supported limit.")
    value = round(value, 4)
    if positive and value <= 0:
        raise ValueError("Amount must be greater than zero.")
    return value

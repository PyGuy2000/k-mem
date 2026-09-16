"""Invoice totals. Rounds each line half-up before summing (ADR-001)."""

from decimal import ROUND_HALF_UP, Decimal

from .tax import rate_for

CENT = Decimal("0.01")


def line_total(quantity: int, unit_price: Decimal, region: str, on: str) -> Decimal:
    gross = (Decimal(quantity) * unit_price) * (1 + rate_for(region, on))
    return gross.quantize(CENT, rounding=ROUND_HALF_UP)


def invoice_total(lines: list[tuple[int, Decimal]], region: str, on: str) -> Decimal:
    return sum((line_total(q, p, region, on) for q, p in lines), Decimal("0"))

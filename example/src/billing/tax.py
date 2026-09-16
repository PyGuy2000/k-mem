"""The tax table: rate by region and effective date (ADR-002)."""

from decimal import Decimal

#: (region, effective_from) -> rate. Data, versioned beside the code.
TABLE: dict[tuple[str, str], Decimal] = {
    ("north", "2026-01-01"): Decimal("0.05"),
    ("north", "2026-07-01"): Decimal("0.06"),
    ("south", "2026-01-01"): Decimal("0.00"),
}


def rate_for(region: str, on: str) -> Decimal:
    rows = sorted((d, r) for (reg, d), r in TABLE.items() if reg == region and d <= on)
    if not rows:
        raise KeyError(f"no rate for {region} on {on}")
    return rows[-1][1]

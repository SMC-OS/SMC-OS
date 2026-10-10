"""Aggregate independently denominated amounts without inventing FX rates."""
from decimal import Decimal, ROUND_HALF_UP
from collections.abc import Iterable


def totals_by_currency(rows: Iterable[tuple[str, object]]) -> dict[str, float]:
    totals: dict[str, Decimal] = {}
    for currency, amount in rows:
        totals[currency] = totals.get(currency, Decimal('0')) + Decimal(str(amount or 0))
    return {currency: float(amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
            for currency, amount in sorted(totals.items())}

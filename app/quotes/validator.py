"""Structured-dimension validation — Sprint 032, Workstream C.

Enforced once, server-side, for every quote-creation path (manual form,
AI draft, legacy /estimate) — never relies on frontend-only checks. Raises
DimensionError with a message safe to show the caller directly.
"""

from app.quotes.models import QuoteRequest

STANDARD_WIDTH_MM = 650  # previous SlabCalculator.DEPTH_M (0.65m), now explicit
SUPPORTED_UNITS = {"mm", "cm", "m"}
_MAX_REALISTIC_LENGTH_MM = 20000  # 20m — generous upper bound; beyond this is almost
                                   # certainly a unit-confusion or AI-parsing error.


class DimensionError(ValueError):
    """Raised for missing/zero/negative/unrealistic/malformed dimensions."""


def validate_dimensions(quote: QuoteRequest) -> None:
    if quote.quantity < 1:
        raise DimensionError("Quantity must be at least 1.")

    if quote.length_mm <= 0:
        raise DimensionError("Length must be greater than zero.")
    if quote.length_mm > _MAX_REALISTIC_LENGTH_MM:
        raise DimensionError(
            f"Length of {quote.length_mm:.0f}mm looks unrealistic — check the unit used."
        )

    if quote.width_mm <= 0:
        raise DimensionError("Width/depth must be greater than zero.")
    if quote.width_mm > _MAX_REALISTIC_LENGTH_MM:
        raise DimensionError(
            f"Width/depth of {quote.width_mm:.0f}mm looks unrealistic — check the unit used."
        )

    if quote.thickness_mm is not None and quote.thickness_mm <= 0:
        raise DimensionError("Thickness must be greater than zero.")

    if quote.unit_input is not None and quote.unit_input not in SUPPORTED_UNITS:
        raise DimensionError(
            f"Unsupported unit '{quote.unit_input}' — use one of {sorted(SUPPORTED_UNITS)}."
        )

    if quote.splashback:
        if quote.splashback_length_mm is None:
            raise DimensionError("Splashback length is required when splashback is selected.")
        if quote.splashback_length_mm <= 0:
            raise DimensionError("Splashback length must be greater than zero.")

    if quote.upstands:
        if quote.upstands_length_mm is None:
            raise DimensionError("Upstand length is required when upstands are selected.")
        if quote.upstands_length_mm <= 0:
            raise DimensionError("Upstand length must be greater than zero.")


def to_mm(value: float, unit: str) -> float:
    """Normalize a raw measurement into canonical millimetres.

    Never guesses a unit — the caller must already know which one `value`
    was expressed in (natural-language parsing resolves this explicitly,
    see app/quotes/ai_draft.py).
    """
    if unit == "mm":
        return value
    if unit == "cm":
        return value * 10
    if unit == "m":
        return value * 1000
    raise DimensionError(f"Unsupported unit '{unit}' — use one of {sorted(SUPPORTED_UNITS)}.")

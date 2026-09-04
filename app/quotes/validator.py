"""Structured-dimension validation — Sprint 032 (single-item), extended in
Sprint 033 to validate each independent line item on a multi-item quote.

Enforced once, server-side, for every quote-creation path (manual form,
AI draft, legacy /estimate) — never relies on frontend-only checks. Raises
DimensionError with a message safe to show the caller directly, including
which item is at fault so the UI can point at the right row.
"""

from app.quotes.models import QuoteItemRequest, QuoteRequest

STANDARD_WIDTH_MM = 650  # previous SlabCalculator.DEPTH_M (0.65m), now explicit
SUPPORTED_UNITS = {"mm", "cm", "m"}
_MAX_REALISTIC_LENGTH_MM = 20000  # 20m — generous upper bound; beyond this is almost
                                   # certainly a unit-confusion or AI-parsing error.


class DimensionError(ValueError):
    """Raised for missing/zero/negative/unrealistic/malformed dimensions."""


def validate_item_dimensions(item: QuoteItemRequest, *, label: str | None = None) -> None:
    prefix = f"{label}: " if label else ""

    if item.quantity < 1:
        raise DimensionError(f"{prefix}Quantity must be at least 1.")

    if item.length_mm <= 0:
        raise DimensionError(f"{prefix}Length must be greater than zero.")
    if item.length_mm > _MAX_REALISTIC_LENGTH_MM:
        raise DimensionError(
            f"{prefix}Length of {item.length_mm:.0f}mm looks unrealistic — check the unit used."
        )

    if item.width_mm <= 0:
        raise DimensionError(f"{prefix}Width/depth must be greater than zero.")
    if item.width_mm > _MAX_REALISTIC_LENGTH_MM:
        raise DimensionError(
            f"{prefix}Width/depth of {item.width_mm:.0f}mm looks unrealistic — check the unit used."
        )

    if item.thickness_mm is not None and item.thickness_mm <= 0:
        raise DimensionError(f"{prefix}Thickness must be greater than zero.")

    if item.unit_input is not None and item.unit_input not in SUPPORTED_UNITS:
        raise DimensionError(
            f"{prefix}Unsupported unit '{item.unit_input}' — use one of {sorted(SUPPORTED_UNITS)}."
        )


def validate_dimensions(quote: QuoteRequest) -> None:
    """Validates every line item on the quote. `quote.items` is always
    populated by this point — QuoteRequest's own model_validator builds
    it from the legacy single-item fields when `items` isn't given
    directly, so there is always at least one item to validate."""
    if not quote.items:
        raise DimensionError("A quote must have at least one item.")

    for index, item in enumerate(quote.items, start=1):
        label = f"Item {index} ({item.item_type})" if len(quote.items) > 1 else None
        validate_item_dimensions(item, label=label)


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

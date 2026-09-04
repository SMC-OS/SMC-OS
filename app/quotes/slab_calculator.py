"""Slab-yield estimate for one quote line item (Sprint 005; per-item since
Sprint 033's multi-line-item architecture — see docs/SPRINTS/sprint-033.md
§2.2). Replaces the Sprint 001 placeholder (`if total_length > 3.2: slabs
= 2 else 1`, no depth, no extras). This is a real area-based formula with
documented constants — an estimate for quoting, not a fabrication-grade
cutting/nesting optimizer. A cutting-list optimizer that accounts for seam
placement, grain/pattern matching, actual slab defects, or sharing slabs
across multiple items of the same material is a materially larger,
separate problem — out of scope here, same boundary Sprint 005 drew for a
single item.

Every item type (worktop/island/splashback/upstand/sill/waterfall_panel/
other) uses this identical quantity x length x width area formula — Sprint
033 removed the old per-feature constants (a fixed island extra-run, a
fixed waterfall panel size, fixed splashback/upstand heights) in favor of
each item simply stating its own real dimensions.
"""

import math

WASTAGE_FACTOR = 1.15  # 15% allowance for cuts, seams, pattern-matching


def calculate_slabs(item, material) -> int:
    """`item` is anything with `.quantity`, `.length_mm`, `.width_mm`
    (a QuoteItemRequest or a QuoteItem row both satisfy this)."""
    area_m2 = (item.length_mm / 1000) * (item.width_mm / 1000) * item.quantity
    required_area = area_m2 * WASTAGE_FACTOR

    slab_length_m, slab_width_m = _parse_slab_size(material.slab_size)
    slab_area = slab_length_m * slab_width_m

    return max(1, math.ceil(required_area / slab_area))


def _parse_slab_size(slab_size: str | None) -> tuple[float, float]:
    """"3200x1600" (mm) -> (3.2, 1.6) (m). Falls back to the standard
    3200x1600 slab if a material's slab_size is missing or malformed."""
    if slab_size:
        try:
            length_mm, width_mm = (int(part) for part in slab_size.lower().split("x"))
            return length_mm / 1000, width_mm / 1000
        except (ValueError, TypeError):
            pass
    return 3.2, 1.6


class SlabCalculator:
    """Thin backward-compatible wrapper — app/quotes/calculator.py calls
    `calculate_slabs` directly for new per-item math; kept as a class too
    since nothing about instantiating one is otherwise deprecated."""

    def calculate(self, item, material) -> int:
        return calculate_slabs(item, material)

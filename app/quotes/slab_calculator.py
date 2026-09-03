"""Slab-yield estimate for a worktop quote (Sprint 005; structured-dimension
inputs since Sprint 032 Workstream C — see docs/SPRINTS/sprint-032.md §2.2).
Replaces the Sprint 001 placeholder (`if total_length > 3.2: slabs = 2 else
1`, no depth, no extras). This is a real area-based formula with documented
constants — an estimate for quoting, not a fabrication-grade cutting/nesting
optimizer. A cutting-list optimizer that accounts for seam placement, grain/
pattern matching, and actual slab defects is a materially larger, separate
problem — out of scope here.

All constants below are business assumptions, not measured data (this
project has no job-history dataset to derive them from) — worth revisiting
once real job outcomes are available to compare against.
"""

import math


class SlabCalculator:
    WASTAGE_FACTOR = 1.15  # 15% allowance for cuts, seams, pattern-matching
    ISLAND_EXTRA_RUN_MM = 1800  # typical extra run an island adds to the total
    WATERFALL_PANEL_AREA_M2 = 0.9 * 0.65  # island-height x depth, per waterfall end
    SPLASHBACK_HEIGHT_MM = 150
    UPSTAND_HEIGHT_MM = 60

    def calculate(self, request, material) -> int:
        length_mm = request.length_mm * request.quantity
        if request.island:
            length_mm += self.ISLAND_EXTRA_RUN_MM

        worktop_area_m2 = (length_mm / 1000) * (request.width_mm / 1000)

        extra_area_m2 = request.waterfall * self.WATERFALL_PANEL_AREA_M2
        if request.splashback and request.splashback_length_mm:
            extra_area_m2 += (request.splashback_length_mm / 1000) * (
                self.SPLASHBACK_HEIGHT_MM / 1000
            )
        if request.upstands and request.upstands_length_mm:
            extra_area_m2 += (request.upstands_length_mm / 1000) * (
                self.UPSTAND_HEIGHT_MM / 1000
            )

        required_area = (worktop_area_m2 + extra_area_m2) * self.WASTAGE_FACTOR

        slab_length_m, slab_width_m = self._parse_slab_size(material.slab_size)
        slab_area = slab_length_m * slab_width_m

        return max(1, math.ceil(required_area / slab_area))

    @staticmethod
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

"""AI Quotation Generator v1 — request/draft schemas.

AIQuoteDraft is deliberately NOT QuoteRequest: every field is optional
(except the two flags with safe False/0 defaults) because incompleteness
must be surfaced to the human reviewer, not silently defaulted. There is no
price/VAT/total field anywhere in this file — the AI extracts structured
fields only, it never computes money (see app/quotes/ai_draft.py's
docstring and docs/DECISIONS.md's new ADR for the full reasoning).

Sprint 032 (Workstream C) adds structured dimensions (quantity/length_mm/
width_mm/thickness_mm/unit_input) in place of the old ambiguous
`kitchen_length`, and a `material_match_status` field ("found"/
"multiple"/"not_found") so the caller can render the same FOUND/MULTIPLE/
NOT_FOUND distinction Workstream B's MaterialSearchService produces — the
AI must never present a guess as if it were a resolved product.
"""

from pydantic import BaseModel, Field


class AIDraftRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class AIQuoteDraft(BaseModel):
    customer: str | None = None

    material: str | None = None
    # What the model actually said, if it didn't match a real catalogue
    # entry — kept for transparency, never used for pricing.
    material_raw: str | None = None
    # "found" | "multiple" | "not_found" | None (nothing mentioned at all).
    material_match_status: str | None = None
    # Populated only when material_match_status == "multiple" — the real
    # candidate names+thicknesses the caller can offer for disambiguation.
    material_candidates: list[str] = Field(default_factory=list)

    thickness: str | None = None

    # Sprint 032 (Workstream C) — structured, unit-normalized dimensions.
    # None (not 0) if not stated in the text — "missing" must stay
    # distinguishable from "mentioned as zero" all the way to the frontend.
    quantity: int | None = None
    length_mm: float | None = None
    width_mm: float | None = None
    thickness_mm: float | None = None
    # What unit the source text actually used, e.g. "mm"/"cm"/"m" — shown
    # back to the user alongside the normalized mm value so a conversion
    # is never silent.
    unit_input: str | None = None

    island: bool = False
    waterfall: int = 0
    splashback: bool = False
    upstands: bool = False
    postcode: str | None = None

    warnings: list[str] = Field(default_factory=list)

"""AI Quotation Generator — request/draft schemas.

Sprint 033 (Workstream C) rewrite: a quote is one or more independent
line items now, so a draft is too. AIQuoteItemDraft mirrors
QuoteItemRequest's shape but every field is optional — incompleteness
must be surfaced to the human reviewer per item, never silently
defaulted or invented. There is no price/VAT/total field anywhere in
this file — the AI extracts structured fields only, it never computes
money (see app/quotes/ai_draft.py's docstring and docs/DECISIONS.md's
ADR-024 for the full reasoning, which still applies unchanged).
"""

from pydantic import BaseModel, Field


class AIDraftRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class AIQuoteItemDraft(BaseModel):
    item_type: str = "worktop"

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

    warnings: list[str] = Field(default_factory=list)


class AIQuoteDraft(BaseModel):
    customer: str | None = None
    postcode: str | None = None

    items: list[AIQuoteItemDraft] = Field(default_factory=list)

    # Quote-level warnings only (e.g. no customer name found at all, or
    # nothing resembling a line item was found in the text) — per-item
    # issues live on that item's own `warnings`.
    warnings: list[str] = Field(default_factory=list)

"""AI Quotation Generator v1 — request/draft schemas.

AIQuoteDraft is deliberately NOT QuoteRequest: every field is optional
(except the two flags with safe False/0 defaults) because incompleteness
must be surfaced to the human reviewer, not silently defaulted. There is no
price/VAT/total field anywhere in this file — the AI extracts structured
fields only, it never computes money (see app/quotes/ai_draft.py's
docstring and docs/DECISIONS.md's new ADR for the full reasoning).
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

    thickness: str | None = None

    # None (not 0) if not stated in the text — "missing" must stay
    # distinguishable from "mentioned as zero" all the way to the frontend.
    kitchen_length: float | None = None

    island: bool = False
    waterfall: int = 0
    splashback: bool = False
    upstands: bool = False
    postcode: str | None = None

    warnings: list[str] = Field(default_factory=list)

"""AIDraftService — AI Quotation Generator (text -> structured multi-item
draft).

Extraction only, never pricing. The structured-output schema has no
price-shaped field at all, so it's structurally impossible for a response
to carry a monetary figure into the rest of the system — not just
instructed not to. See docs/DECISIONS.md's ADR-024 for the full reasoning.

Sprint 033 (Workstream C) rewrite — a quote is one or more independent
line items now (worktop/island/splashback/upstand/sill/waterfall_panel),
so a draft is too. The LLM's job is still purely *language* work: (1)
segmenting the request into distinct items and classifying each one's
type, and (2) copying out, verbatim, the portion of text describing each
item's own quantity/dimensions (its `text_span`) plus any material/
thickness stated specifically for that item — never inheriting one
item's numbers into another's. It never extracts or computes a number
itself. Every `text_span` is re-parsed by app/quotes/dimension_parser.py
— deterministic regex/unit-conversion code — and every material mention
is resolved by app/materials/search.py's MaterialSearchService (Sprint
032, Workstream B), the same canonical retrieval path used everywhere
else in GeoCore. The AI never fabricates a material or a dimension for
any item: a missing, ambiguous, or unrecognised value always comes back
as an explicit per-item warning (or a "multiple"/"not_found" match
status), never a guess.

Three validation layers, unchanged from v1: (1) OpenAI's structured
outputs enforce JSON shape; (2) refusal/error handling never lets a bad
call crash or leak; (3) this service re-resolves every extracted value
against the real catalogue/deterministic parser server-side — the layer
that actually enforces truth, not just shape.

The OpenAI client is constructed lazily, only on first real use, and only
if settings.openai_api_key is set — the app runs fully normally with zero
AI configuration; nothing at import/startup time touches OpenAI.
"""

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.materials.search import material_search_service
from app.quotes.ai_models import AIQuoteDraft, AIQuoteItemDraft
from app.quotes.dimension_parser import parse_dimension_text
from app.quotes.models import ITEM_TYPES

_SYSTEM_PROMPT = (
    "You are an extraction assistant for a stone worktop quoting system. "
    "A request may describe MULTIPLE separate items — a worktop, an "
    "island, one or more splashbacks, upstands, a window sill. Identify "
    "each distinct item mentioned and classify its type as one of: "
    f"{', '.join(sorted(ITEM_TYPES))}. For each item, extract: "
    "`material` and `thickness` ONLY if stated specifically for that "
    "item — leave them null if the item should inherit a material/"
    "thickness mentioned once for the whole quote (put that shared value "
    "in `shared_material`/`shared_thickness` instead, not on every item). "
    "`text_span` must be the exact portion of the original text "
    "describing that item's own quantity and dimensions, copied "
    "verbatim (e.g. 'two 1200 x 600 splashbacks'), so it can be "
    "re-parsed precisely and separately for that item alone. Do NOT "
    "extract or compute any number yourself (quantity, length, width, "
    "thickness-in-mm) beyond copying the text span — that arithmetic "
    "happens separately, in code. Never invent, estimate, or guess a "
    "customer name, material, or an item that isn't present. If a field "
    "is not mentioned, leave it unset (null) rather than guessing."
)


class _AIItemExtraction(BaseModel):
    item_type: str = "worktop"
    material: str | None = None
    thickness: str | None = None
    text_span: str = ""


class _AIExtraction(BaseModel):
    """The literal shape the LLM fills in — no warnings/resolved
    dimensions/match status here, those are computed server-side after
    the model responds (see AIDraftService._build_draft)."""

    customer: str | None = None
    shared_material: str | None = None
    shared_thickness: str | None = None
    items: list[_AIItemExtraction] = Field(default_factory=list)
    postcode: str | None = None


class AIDraftUnavailable(Exception):
    """Raised when no OPENAI_API_KEY is configured. Caught by the router
    and turned into a 503 — the app runs fully normally without one."""


class AIDraftError(Exception):
    """Raised on any OpenAI call failure (network, timeout, rate-limit,
    refusal). Caught by the router and turned into a 502."""


class AIDraftService:
    def __init__(self, client=None) -> None:
        self._client = client

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not settings.openai_api_key:
            raise AIDraftUnavailable("AI quotation drafting is not configured.")

        from openai import OpenAI  # imported lazily — never touches the SDK at startup

        self._client = OpenAI(api_key=settings.openai_api_key)
        return self._client

    def generate(self, db: Session, text: str) -> AIQuoteDraft:
        client = self._get_client()

        try:
            completion = client.chat.completions.parse(
                model=settings.openai_model,
                response_format=_AIExtraction,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
            )
        except Exception as exc:  # network/timeout/API errors of any shape
            raise AIDraftError(str(exc)) from exc

        choice = completion.choices[0]
        if getattr(choice.message, "refusal", None):
            raise AIDraftError("The model declined to process this request.")

        extraction = choice.message.parsed
        if extraction is None:
            raise AIDraftError("The model did not return a parseable response.")

        return self._build_draft(db, extraction)

    def _resolve_item(self, db: Session, item: _AIItemExtraction, extraction: _AIExtraction) -> AIQuoteItemDraft:
        warnings: list[str] = []

        item_type = item.item_type if item.item_type in ITEM_TYPES else "other"

        material_input = item.material or extraction.shared_material
        thickness_input = item.thickness or extraction.shared_thickness

        material_match: str | None = None
        material_raw: str | None = None
        material_match_status: str | None = None
        material_candidates: list[str] = []
        resolved_thickness: str | None = None

        if material_input is None:
            warnings.append("No material found for this item — pick one manually.")
        else:
            # Including the stated thickness in the search query lets the
            # canonical retrieval service (Workstream B) disambiguate
            # between a material's thickness variants automatically —
            # otherwise "Calacatta Gold" alone always ties across its
            # 20mm/30mm rows.
            search_query = material_input
            if thickness_input:
                search_query = f"{material_input} {thickness_input}"

            result = material_search_service.search(db, search_query)
            material_match_status = result.status

            if result.status == "found":
                material_match = result.material.name
                resolved_thickness = result.material.thickness
            elif result.status == "multiple":
                material_raw = material_input
                material_candidates = [
                    f"{m.material.name} ({m.material.thickness})" for m in result.matches
                ]
                warnings.append(
                    f"'{material_input}' matched more than one product — pick one manually."
                )
            else:
                material_raw = material_input
                warnings.append(f"Material '{material_input}' wasn't recognised — pick one manually.")

        dims = parse_dimension_text(item.text_span)

        thickness_value = resolved_thickness
        if thickness_value is None and thickness_input is not None:
            normalized = thickness_input.strip().lower().replace(" ", "")
            thickness_value = normalized if normalized.endswith("mm") else None
        if thickness_value is None and dims.thickness_mm is not None:
            thickness_value = f"{dims.thickness_mm:g}mm"

        if thickness_value is None:
            warnings.append("No thickness found for this item — choose one manually.")

        if dims.length_mm is None:
            warnings.append("No length found for this item — enter dimensions manually.")

        return AIQuoteItemDraft(
            item_type=item_type,
            material=material_match,
            material_raw=material_raw,
            material_match_status=material_match_status,
            material_candidates=material_candidates,
            thickness=thickness_value,
            quantity=dims.quantity,
            length_mm=dims.length_mm,
            width_mm=dims.width_mm,
            thickness_mm=dims.thickness_mm,
            unit_input=dims.unit_input,
            warnings=warnings,
        )

    def _build_draft(self, db: Session, extraction: _AIExtraction) -> AIQuoteDraft:
        warnings: list[str] = []

        if extraction.customer is None:
            warnings.append("No customer name found in the text — enter it manually.")

        if not extraction.items:
            warnings.append("No items found in the text — add at least one manually.")

        items = [self._resolve_item(db, item, extraction) for item in extraction.items]

        return AIQuoteDraft(
            customer=extraction.customer,
            postcode=extraction.postcode,
            items=items,
            warnings=warnings,
        )


ai_draft_service = AIDraftService()

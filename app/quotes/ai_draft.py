"""AIDraftService — AI Quotation Generator v1 (text -> structured draft).

Extraction only, never pricing. The structured-output schema has no
price-shaped field at all, so it's structurally impossible for a response
to carry a monetary figure into the rest of the system — not just
instructed not to. See docs/DECISIONS.md's ADR-024 for the full reasoning
and docs/SPRINTS/sprint-ai-quotation-v1.md for the design writeup.

Sprint 032 (Workstream C) rewrite — the LLM now only extracts *entities*
(customer name, the material as the user referred to it, thickness as
stated, and the boolean job flags). It never extracts or computes a
number used in arithmetic. Every dimension (quantity/length/width/
thickness-in-mm) is parsed from the raw text by
app/quotes/dimension_parser.py — deterministic regex/unit-conversion code,
not the model. Every material mention is resolved by
app/materials/search.py's MaterialSearchService (Sprint 032, Workstream
B) — the same canonical, deterministic retrieval path used everywhere
else in SIMO OS. The AI never fabricates a material or a dimension: a
missing, ambiguous, or unrecognised value always comes back as an
explicit warning (or a "multiple"/"not_found" match status) for the human
reviewer, never a guess.

Three validation layers, unchanged from v1: (1) OpenAI's structured
outputs enforce JSON shape; (2) refusal/error handling never lets a bad
call crash or leak; (3) this service re-resolves every extracted value
against the real catalogue/deterministic parser server-side — the layer
that actually enforces truth, not just shape.

The OpenAI client is constructed lazily, only on first real use, and only
if settings.openai_api_key is set — the app runs fully normally with zero
AI configuration; nothing at import/startup time touches OpenAI.
"""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.materials.search import material_search_service
from app.quotes.ai_models import AIQuoteDraft
from app.quotes.dimension_parser import parse_dimension_text

_SYSTEM_PROMPT = (
    "You are an extraction assistant for a stone worktop quoting system. "
    "Extract ONLY what the user's text explicitly states. Never invent, "
    "estimate, or guess a customer name or a job flag that isn't present. "
    "Extract the material exactly as the user referred to it (e.g. "
    "'Calacatta Oro', 'black quartz', 'SuperGalaxy Diamond Quartz') — do "
    "not correct, guess, or normalize it against any catalogue; that is "
    "resolved separately. Extract thickness only if explicitly stated "
    "(e.g. '20mm'). Do NOT extract any numeric length, width, or "
    "quantity — those are parsed separately by other code. If a field is "
    "not mentioned or is ambiguous, leave it unset (null/false/0 as "
    "appropriate) rather than guessing."
)


class _AIExtraction(BaseModel):
    """The literal shape the LLM fills in — no warnings/dimensions/match
    status here, those are computed server-side after the model responds
    (see AIDraftService._build_draft)."""

    customer: str | None = None
    material: str | None = None
    thickness: str | None = None
    island: bool = False
    waterfall: int = 0
    splashback: bool = False
    upstands: bool = False
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

        return self._build_draft(db, text, extraction)

    def _build_draft(self, db: Session, raw_text: str, extraction: _AIExtraction) -> AIQuoteDraft:
        warnings: list[str] = []

        material_match: str | None = None
        material_raw: str | None = None
        material_match_status: str | None = None
        material_candidates: list[str] = []
        resolved_thickness: str | None = None

        if extraction.material is None:
            warnings.append("No material found in the text — pick one manually.")
        else:
            # Including the stated thickness in the search query lets the
            # canonical retrieval service (Workstream B) disambiguate
            # between a material's thickness variants automatically —
            # otherwise "Calacatta Gold" alone always ties across its
            # 20mm/30mm rows.
            search_query = extraction.material
            if extraction.thickness:
                search_query = f"{extraction.material} {extraction.thickness}"

            result = material_search_service.search(db, search_query)
            material_match_status = result.status

            if result.status == "found":
                material_match = result.material.name
                resolved_thickness = result.material.thickness
            elif result.status == "multiple":
                material_raw = extraction.material
                material_candidates = [
                    f"{m.material.name} ({m.material.thickness})" for m in result.matches
                ]
                warnings.append(
                    f"'{extraction.material}' matched more than one product — pick one manually."
                )
            else:
                material_raw = extraction.material
                warnings.append(
                    f"Material '{extraction.material}' wasn't recognised — pick one manually."
                )

        dims = parse_dimension_text(raw_text)

        thickness_value = resolved_thickness
        if thickness_value is None and extraction.thickness is not None:
            normalized = extraction.thickness.strip().lower().replace(" ", "")
            thickness_value = normalized if normalized.endswith("mm") else None
        if thickness_value is None and dims.thickness_mm is not None:
            thickness_value = f"{dims.thickness_mm:g}mm"

        if thickness_value is None:
            warnings.append("No thickness found in the text — choose one manually.")

        if dims.length_mm is None:
            warnings.append("No length found in the text — enter dimensions manually.")

        if extraction.customer is None:
            warnings.append("No customer name found in the text — enter it manually.")

        return AIQuoteDraft(
            customer=extraction.customer,
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
            island=extraction.island,
            waterfall=extraction.waterfall,
            splashback=extraction.splashback,
            upstands=extraction.upstands,
            postcode=extraction.postcode,
            warnings=warnings,
        )


ai_draft_service = AIDraftService()

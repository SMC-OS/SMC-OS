"""AIDraftService — AI Quotation Generator v1 (text -> structured draft).

Extraction only, never pricing. The structured-output schema has no
price-shaped field at all, so it's structurally impossible for a response
to carry a monetary figure into the rest of the system — not just
instructed not to. See docs/DECISIONS.md's ADR-024 for the full reasoning
and docs/SPRINTS/sprint-ai-quotation-v1.md for the design writeup.

Three validation layers: (1) OpenAI's structured outputs enforce JSON
shape; (2) refusal/error handling never lets a bad call crash or leak;
(3) this service re-validates every extracted value against the real
catalogue/known values server-side — the layer that actually enforces
truth, not just shape.

The OpenAI client is constructed lazily, only on first real use, and only
if settings.openai_api_key is set — the app runs fully normally with zero
AI configuration; nothing at import/startup time touches OpenAI.
"""

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.materials.service import material_service
from app.quotes.ai_models import AIQuoteDraft

_VALID_THICKNESSES = {"20mm", "30mm"}

_SYSTEM_PROMPT_TEMPLATE = (
    "You are an extraction assistant for a stone worktop quoting system. "
    "Extract ONLY what the user's text explicitly states. Never invent, "
    "estimate, or guess a numeric value (lengths, counts) that is not "
    "present in the text. Never invent a material name — only use one "
    "from this exact list, matched by name: {materials}. If a field is "
    "not mentioned or is ambiguous, leave it unset (null/false/0 as "
    "appropriate) rather than guessing."
)


class _AIExtraction(BaseModel):
    """The literal shape the LLM fills in — no warnings/material_raw here,
    those are computed server-side after the model responds (see
    AIDraftService._validate)."""

    customer: str | None = None
    material: str | None = None
    thickness: str | None = None
    kitchen_length: float | None = None
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

        material_names = sorted({m.name for m in material_service.list_all(db)})
        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(materials=", ".join(material_names))

        try:
            completion = client.chat.completions.parse(
                model=settings.openai_model,
                response_format=_AIExtraction,
                messages=[
                    {"role": "system", "content": system_prompt},
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

        return self._validate(extraction, material_names)

    def _validate(self, extraction: _AIExtraction, material_names: list[str]) -> AIQuoteDraft:
        warnings: list[str] = []

        material_match = None
        material_raw = None
        if extraction.material is None:
            warnings.append("No material found in the text — pick one manually.")
        else:
            material_match = next(
                (name for name in material_names if name.lower() == extraction.material.lower()),
                None,
            )
            if material_match is None:
                material_raw = extraction.material
                warnings.append(
                    f"Material '{extraction.material}' wasn't recognised — pick one manually."
                )

        thickness_match = None
        if extraction.thickness is None:
            warnings.append("No thickness found in the text — choose one manually.")
        else:
            normalized = extraction.thickness.strip().lower().replace(" ", "")
            if normalized in _VALID_THICKNESSES:
                thickness_match = normalized
            else:
                warnings.append(
                    f"Thickness '{extraction.thickness}' isn't valid — choose 20mm or 30mm."
                )

        kitchen_length = extraction.kitchen_length
        if kitchen_length is None:
            warnings.append("No kitchen run length found in the text — enter it manually.")
        elif kitchen_length <= 0:
            warnings.append("Kitchen length must be greater than zero — check the value.")
            kitchen_length = None

        if extraction.customer is None:
            warnings.append("No customer name found in the text — enter it manually.")

        return AIQuoteDraft(
            customer=extraction.customer,
            material=material_match,
            material_raw=material_raw,
            thickness=thickness_match,
            kitchen_length=kitchen_length,
            island=extraction.island,
            waterfall=extraction.waterfall,
            splashback=extraction.splashback,
            upstands=extraction.upstands,
            postcode=extraction.postcode,
            warnings=warnings,
        )


ai_draft_service = AIDraftService()

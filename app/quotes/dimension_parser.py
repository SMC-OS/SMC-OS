"""Deterministic natural-language dimension parsing — Sprint 032,
Workstream C.

Understands things like "2400 x 600", "2400mm x 600mm", "2.4m by 600mm",
"two pieces 1200 x 600", "island 2200 x 1000 x 20mm". Every number is
converted to canonical millimetres via app/quotes/validator.py's `to_mm` —
the same conversion the rest of the quote domain uses, so there is exactly
one place unit math happens.

Deliberately not an LLM call: the AI Quotation Generator (app/quotes/
ai_draft.py) extracts the raw dimension phrase from free text via OpenAI's
structured output, then hands it here for actual unit conversion/math —
this module does that arithmetic, never the language model, per this
project's existing "the LLM extracts, code re-validates/computes" pattern
(see ai_draft.py's own module docstring).

Never invents a missing dimension: if a length/width can't be confidently
parsed, the corresponding field is left None so the caller can surface a
"please provide this" warning rather than guessing.
"""

import re
from dataclasses import dataclass

from app.quotes.validator import to_mm

_NUMBER_UNIT = r"(\d+(?:\.\d+)?)\s*(mm|cm|m)?"
_PAIR_RE = re.compile(
    rf"{_NUMBER_UNIT}\s*(?:x|by|×)\s*{_NUMBER_UNIT}(?:\s*(?:x|by|×)\s*{_NUMBER_UNIT})?",
    re.IGNORECASE,
)
_QUANTITY_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_QUANTITY_RE = re.compile(
    r"\b(\d+)\s*(?:pieces?|off|x)\b|"
    r"\b(?:qty|quantity)\s*[:=]?\s*(\d+)\b|"
    r"\b(" + "|".join(_QUANTITY_WORDS) + r")\s*pieces?\b",
    re.IGNORECASE,
)
_THICKNESS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*mm\b", re.IGNORECASE)
# A single standalone measurement with no "x"/"by" pair, e.g. "3.5m
# kitchen run". Unit required (never grabs a bare, unqualified number),
# and deliberately excludes bare "mm" values — in this domain a lone
# "<N>mm" mention is a thickness (handled by _THICKNESS_RE above), never
# a standalone length/width.
_SINGLE_LENGTH_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(cm|m)\b", re.IGNORECASE)


@dataclass
class ParsedDimensions:
    quantity: int | None = None
    length_mm: float | None = None
    width_mm: float | None = None
    thickness_mm: float | None = None
    unit_input: str | None = None


def _to_mm_or_default(value: str, unit: str | None) -> tuple[float, str]:
    resolved_unit = unit.lower() if unit else "mm"
    return to_mm(float(value), resolved_unit), resolved_unit


def parse_dimension_text(text: str) -> ParsedDimensions:
    parsed = ParsedDimensions()

    pair_match = _PAIR_RE.search(text)
    if pair_match:
        l_val, l_unit, w_val, w_unit, t_val, t_unit = pair_match.groups()
        parsed.length_mm, length_unit = _to_mm_or_default(l_val, l_unit)
        parsed.width_mm, _ = _to_mm_or_default(w_val, w_unit)
        parsed.unit_input = l_unit.lower() if l_unit else (w_unit.lower() if w_unit else "mm")
        if t_val is not None:
            parsed.thickness_mm, _ = _to_mm_or_default(t_val, t_unit)
    else:
        single_match = _SINGLE_LENGTH_RE.search(text)
        if single_match:
            value, unit = single_match.groups()
            parsed.length_mm, parsed.unit_input = _to_mm_or_default(value, unit)

    if parsed.thickness_mm is None:
        thickness_match = _THICKNESS_RE.search(text)
        if thickness_match:
            # Avoid double-counting a thickness that was already the third
            # number of an "L x W x T" triple matched above.
            already_used = pair_match and thickness_match.span() == (
                pair_match.start(5), pair_match.end(5)
            ) if pair_match and pair_match.group(5) else False
            if not already_used:
                parsed.thickness_mm = float(thickness_match.group(1))

    quantity_match = _QUANTITY_RE.search(text)
    if quantity_match:
        digit_a, digit_b, word = quantity_match.groups()
        if digit_a is not None:
            parsed.quantity = int(digit_a)
        elif digit_b is not None:
            parsed.quantity = int(digit_b)
        elif word is not None:
            parsed.quantity = _QUANTITY_WORDS[word.lower()]

    return parsed

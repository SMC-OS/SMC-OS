"""Free-text catalogue search vocabulary (Phase A — catalogue remediation).

A quoter types what they would say to a customer — "white quartz",
"black granite", "grey sintered" — not the catalogue's internal
`material_family`/`colour_family` keys. This module turns one typed word
into the structured values it means, so the search in
app/database/crud.py can match a family or colour by meaning rather than
by an accidental substring of a product name.

Pure functions only: no database access, trivially unit-testable.
"""

import re

from app.catalogue.models import MATERIAL_FAMILIES

# Words a quoter actually types, mapped to the catalogue's own
# material_family keys. Every family key also matches itself (added
# below), so this table only needs the words that differ from the key.
_FAMILY_SYNONYMS: dict[str, set[str]] = {
    "sintered": {"sintered_stone"},
    "ultracompact": {"sintered_stone"},
    "engineered": {"quartz", "other_engineered_surface"},
    "natural": {"granite", "marble", "quartzite", "onyx", "other_natural_stone"},
    "tile": {"porcelain", "ceramic"},
}

# Colour families as stored on CatalogueSurface.colour_family, plus the
# spellings and near-synonyms a UK or US user types for them.
_COLOUR_SYNONYMS: dict[str, set[str]] = {
    "white": {"white"},
    "black": {"black"},
    "grey": {"grey"},
    "gray": {"grey"},
    "beige": {"beige"},
    "cream": {"beige"},
    "ivory": {"beige"},
    "brown": {"brown"},
    "blue": {"blue"},
    "green": {"green"},
    "gold": {"gold"},
    "red": {"red"},
}

# A search never needs more than a handful of words; capping this keeps
# the generated SQL bounded no matter what is pasted into the box.
MAX_TOKENS = 6


def tokenize(query: str | None) -> list[str]:
    """Splits a free-text query into lower-case words. Commas, slashes
    and repeated whitespace are separators; empty tokens are dropped and
    duplicates collapse, preserving first-seen order."""
    if not query:
        return []
    seen: list[str] = []
    for token in re.split(r"[\s,/]+", query.strip().lower()):
        if token and token not in seen:
            seen.append(token)
    return seen[:MAX_TOKENS]


def families_for(token: str) -> set[str]:
    """The material_family keys a single typed word refers to — empty
    when the word is not a family word at all."""
    token = token.lower()
    families = set(_FAMILY_SYNONYMS.get(token, set()))
    if token in MATERIAL_FAMILIES:
        families.add(token)
    return families


def colours_for(token: str) -> set[str]:
    """The colour_family values a single typed word refers to — empty
    when the word is not a colour word."""
    return set(_COLOUR_SYNONYMS.get(token.lower(), set()))

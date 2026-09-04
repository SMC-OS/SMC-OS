"""MaterialSearchService — Sprint 032, Workstream B.

The single canonical, deterministic material/product retrieval path for
GeoCore. Every assistant/quote surface that needs to resolve a material
from natural language goes through this service (`material_search_service`
below) — no other module may reimplement name/category/thickness matching
logic (see docs/SPRINTS/sprint-032.md §2.1). `MaterialService.
get_by_name_and_thickness` (app/materials/service.py) is a different,
narrower thing — an exact-key lookup once a material has *already* been
resolved (e.g. a validated dropdown selection) — and stays as-is; it is
not a competing search implementation.

Retrieval is entirely rule-based: normalization, tokenization, explicit
thickness extraction, and substring/token-overlap/fuzzy scoring against
name/category/finish. It never calls an LLM and never guesses. There are
exactly three outcomes, surfaced via `MaterialSearchResult.status`:

- "found" — exactly one confident match. `.material` is the resolved row.
- "multiple" — several real, scored candidates; the caller must
  disambiguate (present them, or ask a follow-up question) rather than
  silently pick one.
- "not_found" — nothing cleared the candidate bar. Callers must say so
  explicitly and must never fabricate a result.

`materials` is a shared, tenant-agnostic reference catalogue (ADR-029,
app/database/crud.py) — this service never touches tenant-owned tables,
so tenant isolation is preserved by construction; there is no tenant_id
parameter here because there is nothing tenant-scoped to leak.
"""

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.database.models import Material
from app.materials.service import material_service

# Generic/filler words stripped before matching so they don't dilute
# token-overlap scoring — none of these ever appear in a material name,
# category, or finish in the seeded catalogue.
_STOPWORDS = {
    "a", "an", "the", "do", "we", "have", "has", "is", "are", "of", "for",
    "to", "in", "on", "at", "find", "show", "me", "please", "you", "got",
    "any", "all", "available", "product", "products", "material",
    "materials", "item", "items", "stock", "get", "need", "want",
    "looking", "search", "list", "our", "us", "with", "and", "or",
}

# A name/category match alone must clear this to be considered a real
# candidate at all.
_CANDIDATE_THRESHOLD = 0.45
# To resolve automatically to a single "found" result (rather than
# surfacing every candidate), the top scorer must be both confident in
# absolute terms and clearly ahead of the next-best candidate.
_CONFIDENT_MIN = 0.75
_CONFIDENT_MARGIN = 0.25
# When surfacing "multiple" candidates, only include rows within this
# margin of the top score — keeps a strong exact/partial match (e.g. "the
# Gold variants") from getting diluted by weaker, unrelated matches that
# merely cleared the candidate floor.
_MULTIPLE_BAND = 0.15

_THICKNESS_RE = re.compile(r"(\d+)\s*mm")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def _extract_thickness(normalized_query: str) -> str | None:
    match = _THICKNESS_RE.search(normalized_query)
    return f"{match.group(1)}mm" if match else None


@dataclass
class MaterialMatch:
    material: Material
    score: float


@dataclass
class MaterialSearchResult:
    status: str  # "found" | "multiple" | "not_found"
    matches: list[MaterialMatch] = field(default_factory=list)

    @property
    def material(self) -> Material | None:
        """The resolved row — only meaningful when status == "found"."""
        return self.matches[0].material if self.status == "found" and self.matches else None


class MaterialSearchService:
    def search(self, db: Session, query: str) -> MaterialSearchResult:
        materials = material_service.list_all(db)
        if not materials:
            return MaterialSearchResult(status="not_found")

        normalized_query = _normalize(query)
        thickness_filter = _extract_thickness(normalized_query)
        query_no_thickness = _THICKNESS_RE.sub(" ", normalized_query)
        query_tokens = _tokens(query_no_thickness)
        filtered_tokens = [t for t in query_tokens if t not in _STOPWORDS]

        category_vocab = {m.category.lower() for m in materials if m.category}

        # Pure category/type browse ("quartz", "show all available
        # marble", "20mm granite") — every meaningful token names a known
        # category, so list that category's real rows rather than
        # scoring name similarity against them.
        if (filtered_tokens and all(t in category_vocab for t in filtered_tokens)) or (
            not filtered_tokens and thickness_filter is not None and not category_vocab.isdisjoint(query_tokens)
        ):
            category_words = set(filtered_tokens) or (category_vocab & set(query_tokens))
            return self._category_browse(materials, category_words, thickness_filter)

        # Pure thickness browse ("20mm") — no name/category token at all.
        if not filtered_tokens and thickness_filter is not None:
            matches = [
                MaterialMatch(m, 1.0)
                for m in materials
                if m.thickness and m.thickness.lower() == thickness_filter
            ]
            return self._classify(matches)

        return self._name_search(materials, filtered_tokens, thickness_filter, category_vocab)

    def _category_browse(
        self,
        materials: list[Material],
        category_words: set[str],
        thickness_filter: str | None,
    ) -> MaterialSearchResult:
        matches = [
            MaterialMatch(m, 1.0)
            for m in materials
            if m.category
            and m.category.lower() in category_words
            and (thickness_filter is None or (m.thickness and m.thickness.lower() == thickness_filter))
        ]
        return self._classify(matches)

    def _name_search(
        self,
        materials: list[Material],
        filtered_tokens: list[str],
        thickness_filter: str | None,
        category_vocab: set[str],
    ) -> MaterialSearchResult:
        if not filtered_tokens and thickness_filter is None:
            return MaterialSearchResult(status="not_found")

        query_clean = " ".join(filtered_tokens)
        scored: list[MaterialMatch] = []

        for m in materials:
            name_norm = _normalize(m.name)
            name_tokens = _tokens(name_norm)

            if filtered_tokens:
                if query_clean == name_norm:
                    name_score = 1.0
                elif query_clean in name_norm or name_norm in query_clean:
                    name_score = 0.85
                else:
                    overlap = len(set(filtered_tokens) & set(name_tokens)) / max(1, len(filtered_tokens))
                    ratio = SequenceMatcher(None, query_clean, name_norm).ratio()
                    name_score = 0.6 * overlap + 0.4 * ratio
            else:
                name_score = 0.0

            score = name_score

            if m.category:
                cat = m.category.lower()
                if cat in filtered_tokens:
                    score += 0.15
                elif category_vocab & set(filtered_tokens) - {cat}:
                    # The query names a *different* real category than
                    # this row's — a strong "wrong type" signal (e.g.
                    # "black quartz" naming Granite's "Absolute Black").
                    score -= 0.4

            if thickness_filter is not None and m.thickness:
                if m.thickness.lower() == thickness_filter:
                    score += 0.2
                else:
                    score -= 0.5

            if m.finish and m.finish.lower() in filtered_tokens:
                score += 0.1

            if score >= _CANDIDATE_THRESHOLD:
                scored.append(MaterialMatch(m, score))

        return self._classify(scored)

    def _classify(self, matches: list[MaterialMatch]) -> MaterialSearchResult:
        if not matches:
            return MaterialSearchResult(status="not_found")

        matches.sort(key=lambda mm: mm.score, reverse=True)

        if len(matches) == 1:
            return MaterialSearchResult(status="found", matches=matches)

        top, second = matches[0], matches[1]
        if top.score >= _CONFIDENT_MIN and (top.score - second.score) >= _CONFIDENT_MARGIN:
            return MaterialSearchResult(status="found", matches=[top])

        close_matches = [mm for mm in matches if top.score - mm.score <= _MULTIPLE_BAND]
        return MaterialSearchResult(status="multiple", matches=close_matches)


material_search_service = MaterialSearchService()

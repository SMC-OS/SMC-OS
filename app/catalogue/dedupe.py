"""Safe deduplication identity for the master catalogue (Sprint 042,
Task 2). A surface's visible name is never a safe identity — "Calacatta
Gold" legitimately exists under more than one supplier or brand.
Candidate matching considers manufacturer, brand, collection, canonical
name, supplier, supplier SKU, manufacturer SKU and thickness/finish
overlap — never name alone.

This module only *scores* candidates; it never merges. Merge approval
stays an explicit, separate action (the Master Spec's own words: "merge
approval remains explicit") — out of scope for Plan 03's seed pipeline,
which only needs to warn, not act.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SurfaceIdentity:
    """The identity fields a candidate-duplicate check compares — either
    a real CatalogueSurface row or a not-yet-created import candidate."""

    canonical_name: str
    material_family: str
    supplier_id: str | None = None
    manufacturer_id: str | None = None
    brand_id: str | None = None
    collection_id: str | None = None
    supplier_sku: str | None = None
    manufacturer_sku: str | None = None
    thicknesses_mm: frozenset[float] = field(default_factory=frozenset)
    finishes: frozenset[str] = field(default_factory=frozenset)


def _normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def score_candidate_match(a: SurfaceIdentity, b: SurfaceIdentity) -> float:
    """Returns a 0.0-1.0 confidence that `a` and `b` are the same real
    surface. Different material_family is an immediate hard 0.0 — a
    quartz and a marble product are never the same surface regardless
    of anything else matching. An exact SKU match under the SAME
    supplier or manufacturer is decisive (0.95+); everything else is a
    weighted combination of the identity fields above. Name similarity
    alone can never reach the "safe duplicate" threshold on its own —
    see test_dedupe.py for the exact case this guards (two same-named
    products under different suppliers must NOT score as a match)."""

    if a.material_family != b.material_family:
        return 0.0

    # A SKU match is only meaningful within the same commercial
    # relationship — two different suppliers using the same SKU space
    # is coincidence, not identity.
    if (
        a.supplier_sku
        and b.supplier_sku
        and a.supplier_sku == b.supplier_sku
        and a.supplier_id
        and a.supplier_id == b.supplier_id
    ):
        return 0.97
    if (
        a.manufacturer_sku
        and b.manufacturer_sku
        and a.manufacturer_sku == b.manufacturer_sku
        and a.manufacturer_id
        and a.manufacturer_id == b.manufacturer_id
    ):
        return 0.97

    score = 0.0
    weight_total = 0.0

    def add(weight: float, matched: bool, applicable: bool) -> None:
        # Only counted when BOTH identities actually specify the field —
        # neither side knowing a surface's supplier is uninformative and
        # must not dilute the score the way a genuine mismatch would.
        nonlocal score, weight_total
        if not applicable:
            return
        weight_total += weight
        if matched:
            score += weight

    add(0.30, _normalize_name(a.canonical_name) == _normalize_name(b.canonical_name), True)
    add(0.20, a.supplier_id == b.supplier_id, a.supplier_id is not None and b.supplier_id is not None)
    add(
        0.20,
        a.manufacturer_id == b.manufacturer_id,
        a.manufacturer_id is not None and b.manufacturer_id is not None,
    )
    add(0.10, a.brand_id == b.brand_id, a.brand_id is not None and b.brand_id is not None)
    add(
        0.05,
        a.collection_id == b.collection_id,
        a.collection_id is not None and b.collection_id is not None,
    )
    add(0.10, bool(a.thicknesses_mm & b.thicknesses_mm), bool(a.thicknesses_mm and b.thicknesses_mm))
    add(0.05, bool(a.finishes & b.finishes), bool(a.finishes and b.finishes))

    if weight_total == 0:
        return 0.0

    normalized = score / weight_total
    # Same name but no shared supplier/manufacturer/brand/collection
    # identity at all is exactly the legitimate-coexistence case (the
    # same visible product name from two unrelated suppliers) — cap
    # below the "likely duplicate" threshold even if every other signal
    # happens to align by coincidence (e.g. both 20mm polished).
    same_name = _normalize_name(a.canonical_name) == _normalize_name(b.canonical_name)
    no_shared_owner = (
        not (a.supplier_id and a.supplier_id == b.supplier_id)
        and not (a.manufacturer_id and a.manufacturer_id == b.manufacturer_id)
        and not (a.brand_id and a.brand_id == b.brand_id)
    )
    if same_name and no_shared_owner:
        return min(normalized, 0.4)

    return normalized


DUPLICATE_CANDIDATE_THRESHOLD = 0.75


def find_candidate_duplicates(
    candidate: SurfaceIdentity, existing: list[tuple[str, SurfaceIdentity]]
) -> list[tuple[str, float]]:
    """`existing` is a list of (id, identity) pairs — typically every
    active surface already in the catalogue. Returns (id, score) pairs
    at or above the threshold, highest score first. Never merges;
    callers (the import pipeline, Task 11) surface these for explicit
    human review."""

    scored = [
        (existing_id, score_candidate_match(candidate, identity)) for existing_id, identity in existing
    ]
    matches = [(eid, score) for eid, score in scored if score >= DUPLICATE_CANDIDATE_THRESHOLD]
    return sorted(matches, key=lambda pair: pair[1], reverse=True)

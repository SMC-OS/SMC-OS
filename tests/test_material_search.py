"""Regression tests for MaterialSearchService (Sprint 032, Workstream B) —
the single canonical retrieval path every assistant/quote surface must use.

Exercised against the real seeded catalogue (app/materials/seed.py) via the
`db` fixture, since that's what every caller actually queries against.
"""

from app.materials.search import material_search_service


def test_exact_name_with_thickness_returns_found(db):
    result = material_search_service.search(db, "Calacatta Gold 20mm")
    assert result.status == "found"
    assert result.material.name == "Calacatta Gold"
    assert result.material.thickness == "20mm"
    assert result.material.price == 2650


def test_exact_name_without_thickness_returns_multiple_thickness_variants(db):
    result = material_search_service.search(db, "Calacatta Gold")
    assert result.status == "multiple"
    names = {m.material.name for m in result.matches}
    thicknesses = {m.material.thickness for m in result.matches}
    assert names == {"Calacatta Gold"}
    assert thicknesses == {"20mm", "30mm"}


def test_partial_name_matches_multiple_real_products(db):
    result = material_search_service.search(db, "Calacatta")
    assert result.status == "multiple"
    names = {m.material.name for m in result.matches}
    assert names == {"Calacatta Gold", "Calacatta Oro", "Calacatta Porcelain"}


def test_case_and_spacing_insensitive(db):
    result = material_search_service.search(db, "  CALACATTA   GOLD   20MM  ")
    assert result.status == "found"
    assert result.material.name == "Calacatta Gold"
    assert result.material.thickness == "20mm"


def test_case_and_spacing_insensitive_partial(db):
    exact = material_search_service.search(db, "Nero Marquina 30mm")
    messy = material_search_service.search(db, " nero    MARQUINA 30 mm ")
    assert messy.status == "found"
    assert messy.material.id == exact.material.id


def test_category_search_returns_every_matching_row(db):
    result = material_search_service.search(db, "quartz")
    assert result.status == "multiple"
    assert len(result.matches) == 10  # 5 quartz products x 2 thicknesses
    assert all(m.material.category == "Quartz" for m in result.matches)


def test_category_and_thickness_combo(db):
    result = material_search_service.search(db, "20mm quartz")
    assert result.status == "multiple"
    assert len(result.matches) == 5
    assert all(m.material.category == "Quartz" for m in result.matches)
    assert all(m.material.thickness == "20mm" for m in result.matches)


def test_thickness_only_search_browses_by_thickness(db):
    result = material_search_service.search(db, "30mm")
    assert result.status == "multiple"
    assert all(m.material.thickness == "30mm" for m in result.matches)
    assert len(result.matches) >= 10


def test_material_plus_thickness_resolves_correct_priced_row(db):
    result = material_search_service.search(db, "Nero Marquina 30mm")
    assert result.status == "found"
    assert result.material.thickness == "30mm"
    thirty_mm_price = result.material.price

    twenty = material_search_service.search(db, "Nero Marquina 20mm")
    assert twenty.status == "found"
    assert twenty.material.price < thirty_mm_price


def test_ambiguous_natural_language_query_returns_real_candidates(db):
    result = material_search_service.search(db, "Do we have Carrara?")
    assert result.status == "multiple"
    names = {m.material.name for m in result.matches}
    assert names == {"Carrara Mist", "Carrara White"}


def test_missing_product_returns_not_found_never_fabricated(db):
    result = material_search_service.search(db, "SuperGalaxy Diamond Quartz")
    assert result.status == "not_found"
    assert result.material is None
    assert result.matches == []


def test_mismatched_category_combo_returns_not_found(db):
    # "Absolute Black" is Granite, not Quartz — the AI must not present it
    # as a match for a category it explicitly isn't.
    result = material_search_service.search(db, "black quartz")
    assert result.status == "not_found"


def test_meaningless_query_returns_not_found(db):
    result = material_search_service.search(db, "???")
    assert result.status == "not_found"


def test_results_are_always_real_catalogue_rows(db):
    from app.materials.service import material_service

    real_ids = {m.id for m in material_service.list_all(db)}
    for query in ("quartz", "Calacatta", "Carrara", "20mm"):
        result = material_search_service.search(db, query)
        for match in result.matches:
            assert match.material.id in real_ids

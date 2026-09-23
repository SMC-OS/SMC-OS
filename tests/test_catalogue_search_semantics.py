"""Phase A — catalogue search semantics.

Free text matches what a surface *is* (its name, brand, manufacturer,
material family and colour, by meaning), every typed word must match,
and a supplier matches only a surface it genuinely sources for the
searching tenant.
"""

import uuid

import pytest
from sqlalchemy import delete

from app.catalogue import search_terms
from app.catalogue.service import catalogue_service
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    CatalogueSupplier,
    CatalogueSurface,
    CatalogueSurfaceVariant,
    Subscription,
    Tenant,
    TenantCatalogueOverride,
)
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service

RUN = uuid.uuid4().hex[:8]


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _surface(db, name, *, family, colour, tenant_id=None, supplier_id=None):
    return crud.create_catalogue_surface(
        db,
        tenant_id=tenant_id,
        supplier_id=supplier_id,
        manufacturer_id=None,
        brand_id=None,
        collection_id=None,
        canonical_name=name,
        slug=f"pytest-semantics-{uuid.uuid4().hex[:10]}",
        supplier_sku=None,
        manufacturer_sku=None,
        material_family=family,
        colour_family=colour,
        pattern_family=None,
        origin_country=None,
        active=True,
        discontinued=False,
        source_url=None,
        source_name="pytest",
        source_verified_at=None,
    )


def _ids(results):
    return {s.id for s in results}


@pytest.fixture()
def tenants(db):
    a = tenant_service.create(db, TenantCreate(name=f"SearchSemanticsA {RUN}"))
    b = tenant_service.create(db, TenantCreate(name=f"SearchSemanticsB {RUN}"))
    created_surfaces: list = []
    created_suppliers: list = []
    yield a, b, created_surfaces, created_suppliers
    cleanup = SessionLocal()
    try:
        cleanup.execute(delete(TenantCatalogueOverride).where(TenantCatalogueOverride.tenant_id.in_([a.id, b.id])))
        if created_surfaces:
            cleanup.execute(
                delete(CatalogueSurfaceVariant).where(CatalogueSurfaceVariant.surface_id.in_(created_surfaces))
            )
            cleanup.execute(delete(CatalogueSurface).where(CatalogueSurface.id.in_(created_surfaces)))
        if created_suppliers:
            cleanup.execute(delete(CatalogueSupplier).where(CatalogueSupplier.id.in_(created_suppliers)))
        cleanup.execute(delete(ActivityLog).where(ActivityLog.tenant_id.in_([a.id, b.id])))
        cleanup.execute(delete(Subscription).where(Subscription.tenant_id.in_([a.id, b.id])))
        cleanup.execute(delete(Tenant).where(Tenant.id.in_([a.id, b.id])))
        cleanup.commit()
    finally:
        cleanup.close()


# --- Vocabulary (pure) -------------------------------------------------------


def test_tokenize_lowercases_splits_and_deduplicates():
    assert search_terms.tokenize("  White, QUARTZ / white  ") == ["white", "quartz"]
    assert search_terms.tokenize("") == []
    assert search_terms.tokenize(None) == []


def test_tokenize_caps_the_number_of_words():
    assert len(search_terms.tokenize("a b c d e f g h i j")) == search_terms.MAX_TOKENS


def test_family_words_map_to_catalogue_families():
    assert search_terms.families_for("Quartz") == {"quartz"}
    assert search_terms.families_for("granite") == {"granite"}
    assert search_terms.families_for("marble") == {"marble"}
    assert search_terms.families_for("sintered") == {"sintered_stone"}
    assert search_terms.families_for("calacatta") == set()


def test_colour_words_map_uk_and_us_spellings():
    assert search_terms.colours_for("grey") == {"grey"}
    assert search_terms.colours_for("gray") == {"grey"}
    assert search_terms.colours_for("cream") == {"beige"}
    assert search_terms.colours_for("quartz") == set()


# --- Material family and colour search --------------------------------------


def test_family_word_finds_surfaces_whose_name_never_mentions_it(db, tenants):
    a, _, surfaces, _ = tenants
    granite = _surface(db, f"Kashmir Frost {RUN}", family="granite", colour="white", tenant_id=a.id)
    quartz = _surface(db, f"Kashmir Glow {RUN}", family="quartz", colour="white", tenant_id=a.id)
    surfaces += [granite.id, quartz.id]

    results = _ids(catalogue_service.search(db, a.id, query=f"granite {RUN}", limit=50))
    assert granite.id in results
    assert quartz.id not in results


def test_every_word_must_match_so_colour_plus_family_narrows(db, tenants):
    a, _, surfaces, _ = tenants
    white_quartz = _surface(db, f"Alpha {RUN}", family="quartz", colour="white", tenant_id=a.id)
    grey_quartz = _surface(db, f"Bravo {RUN}", family="quartz", colour="grey", tenant_id=a.id)
    white_marble = _surface(db, f"Charlie {RUN}", family="marble", colour="white", tenant_id=a.id)
    surfaces += [white_quartz.id, grey_quartz.id, white_marble.id]

    results = _ids(catalogue_service.search(db, a.id, query=f"white quartz {RUN}", limit=50))
    assert results == {white_quartz.id}


def test_us_spelling_of_a_colour_finds_the_uk_colour_family(db, tenants):
    a, _, surfaces, _ = tenants
    grey = _surface(db, f"Delta {RUN}", family="porcelain", colour="grey", tenant_id=a.id)
    surfaces.append(grey.id)

    assert grey.id in _ids(catalogue_service.search(db, a.id, query=f"gray {RUN}", limit=50))


def test_name_search_still_works_for_multi_word_names(db, tenants):
    a, _, surfaces, _ = tenants
    named = _surface(db, f"Calacatta Gold {RUN}", family="quartz", colour="white", tenant_id=a.id)
    surfaces.append(named.id)

    assert named.id in _ids(catalogue_service.search(db, a.id, query=f"calacatta gold {RUN}", limit=50))
    assert named.id not in _ids(catalogue_service.search(db, a.id, query=f"calacatta silver {RUN}", limit=50))


# --- Supplier semantics ------------------------------------------------------


def test_supplier_matches_a_surface_it_supplies_in_the_catalogue(db, tenants):
    a, _, surfaces, suppliers = tenants
    supplier = crud.create_catalogue_supplier(db, name=f"StoneHouse{RUN}", slug=f"stonehouse-{RUN}", active=True)
    suppliers.append(supplier.id)
    supplied = _surface(db, f"Echo {RUN}", family="quartz", colour="white", tenant_id=a.id, supplier_id=supplier.id)
    unrelated = _surface(db, f"Foxtrot {RUN}", family="quartz", colour="white", tenant_id=a.id)
    surfaces += [supplied.id, unrelated.id]

    by_name = _ids(catalogue_service.search(db, a.id, query=f"StoneHouse{RUN}", limit=50))
    assert by_name == {supplied.id}

    by_filter = _ids(catalogue_service.search(db, a.id, supplier_id=supplier.id, limit=50))
    assert by_filter == {supplied.id}


def test_supplier_matches_through_the_tenants_own_preferred_supplier_only(db, tenants):
    a, b, surfaces, suppliers = tenants
    supplier = crud.create_catalogue_supplier(db, name=f"Merchant{RUN}", slug=f"merchant-{RUN}", active=True)
    suppliers.append(supplier.id)
    shared = _surface(db, f"Golf {RUN}", family="granite", colour="black")
    surfaces.append(shared.id)
    crud.upsert_tenant_catalogue_override(
        db, tenant_id=a.id, surface_id=shared.id, surface_variant_id=None, preferred_supplier_id=supplier.id
    )

    assert shared.id in _ids(catalogue_service.search(db, a.id, query=f"Merchant{RUN}", limit=50))
    assert shared.id in _ids(catalogue_service.search(db, a.id, supplier_id=supplier.id, limit=50))
    # Tenant B never chose that supplier, so it must not see the match.
    assert shared.id not in _ids(catalogue_service.search(db, b.id, query=f"Merchant{RUN}", limit=50))
    assert shared.id not in _ids(catalogue_service.search(db, b.id, supplier_id=supplier.id, limit=50))


def test_supplier_with_no_sourcing_link_matches_nothing(db, tenants):
    a, _, surfaces, suppliers = tenants
    supplier = crud.create_catalogue_supplier(db, name=f"Nobody{RUN}", slug=f"nobody-{RUN}", active=True)
    suppliers.append(supplier.id)
    surfaces.append(_surface(db, f"Hotel {RUN}", family="quartz", colour="white", tenant_id=a.id).id)

    assert catalogue_service.search(db, a.id, query=f"Nobody{RUN}", limit=50) == []
    assert catalogue_service.search(db, a.id, supplier_id=supplier.id, limit=50) == []


def test_several_variant_overrides_still_return_the_surface_once(db, tenants):
    a, _, surfaces, suppliers = tenants
    supplier = crud.create_catalogue_supplier(db, name=f"Dupe{RUN}", slug=f"dupe-{RUN}", active=True)
    suppliers.append(supplier.id)
    surface = _surface(db, f"India {RUN}", family="quartz", colour="white")
    surfaces.append(surface.id)
    v20 = crud.create_catalogue_surface_variant(
        db, surface_id=surface.id, thickness_mm=20.0, finish="Polished",
        slab_length_mm=3200, slab_width_mm=1600, supplier_variant_sku=None, active=True,
    )
    v30 = crud.create_catalogue_surface_variant(
        db, surface_id=surface.id, thickness_mm=30.0, finish="Polished",
        slab_length_mm=3200, slab_width_mm=1600, supplier_variant_sku=None, active=True,
    )
    for variant in (v20, v30):
        crud.upsert_tenant_catalogue_override(
            db, tenant_id=a.id, surface_id=surface.id, surface_variant_id=variant.id,
            preferred_supplier_id=supplier.id,
        )

    results = catalogue_service.search(db, a.id, query=f"Dupe{RUN}", limit=50)
    assert [s.id for s in results] == [surface.id]

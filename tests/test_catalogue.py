"""GeoCore Premium OS Plan 03 (Sprint 042) — Master Materials & Supplier
Catalogue + Stone Quote Engine V2.
"""

import uuid

import pytest
from sqlalchemy import delete

from app.auth.service import auth_service
from app.catalogue.dedupe import SurfaceIdentity, find_candidate_duplicates, score_candidate_match
from app.catalogue.service import SurfaceNotFoundError, catalogue_service, resolve_price_per_slab
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    CatalogueSurface,
    CatalogueSurfaceVariant,
    Quote,
    QuoteItem,
    Subscription,
    Tenant,
    TenantCatalogueOverride,
    User,
)
from app.tenants.models import TenantCreate
from app.tenants.service import tenant_service

RUN_ID = uuid.uuid4().hex[:8]
STRONG_PASSWORD = "Catalogue-Test-Password-1!"


def _unique_email(label: str) -> str:
    return f"pytest-catalogue-{RUN_ID}-{label}-{uuid.uuid4().hex[:6]}@example.invalid"


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_tenant(db, name: str) -> Tenant:
    return tenant_service.create(db, TenantCreate(name=f"{name} {RUN_ID}"))


def _make_owner_headers(client, db, tenant: Tenant, label: str) -> dict:
    email = _unique_email(label)
    auth_service.create_user(
        db, tenant_id=tenant.id, name="Pytest Catalogue Owner", email=email, password=STRONG_PASSWORD, role="Owner"
    )
    login = client.post("/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _seed_surface(db, *, tenant_id=None, name="Pytest Calacatta Gold", family="quartz") -> CatalogueSurface:
    return crud.create_catalogue_surface(
        db,
        tenant_id=tenant_id,
        supplier_id=None,
        manufacturer_id=None,
        brand_id=None,
        collection_id=None,
        canonical_name=name,
        slug=f"pytest-{uuid.uuid4().hex[:10]}",
        supplier_sku=None,
        manufacturer_sku=None,
        material_family=family,
        colour_family=None,
        pattern_family=None,
        origin_country=None,
        active=True,
        discontinued=False,
        source_url=None,
        source_name="pytest",
        source_verified_at=None,
    )


def _seed_variant(db, surface_id, *, thickness_mm=20.0, finish="Polished", slab_length_mm=3200, slab_width_mm=1600):
    return crud.create_catalogue_surface_variant(
        db,
        surface_id=surface_id,
        thickness_mm=thickness_mm,
        finish=finish,
        slab_length_mm=slab_length_mm,
        slab_width_mm=slab_width_mm,
        supplier_variant_sku=None,
        active=True,
    )


def _cleanup_tenant(tenant_id, extra_surface_ids: list = None):
    db = SessionLocal()
    try:
        surface_ids = list(extra_surface_ids or [])
        surface_ids += [
            row[0] for row in db.query(CatalogueSurface.id).filter(CatalogueSurface.tenant_id == tenant_id).all()
        ]
        if surface_ids:
            db.execute(
                delete(QuoteItem).where(QuoteItem.catalogue_surface_id.in_(surface_ids))
            )
            db.execute(delete(TenantCatalogueOverride).where(TenantCatalogueOverride.surface_id.in_(surface_ids)))
            db.execute(
                delete(CatalogueSurfaceVariant).where(CatalogueSurfaceVariant.surface_id.in_(surface_ids))
            )
            db.execute(delete(CatalogueSurface).where(CatalogueSurface.id.in_(surface_ids)))
        db.execute(delete(TenantCatalogueOverride).where(TenantCatalogueOverride.tenant_id == tenant_id))
        db.execute(delete(Quote).where(Quote.tenant_id == tenant_id))
        db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant_id))
        db.execute(delete(Subscription).where(Subscription.tenant_id == tenant_id))
        db.execute(delete(User).where(User.tenant_id == tenant_id))
        db.execute(delete(Tenant).where(Tenant.id == tenant_id))
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Task 2 — safe deduplication identity
# ---------------------------------------------------------------------------


def test_same_visible_name_under_different_suppliers_does_not_score_as_a_duplicate():
    a = SurfaceIdentity(canonical_name="Calacatta Gold", material_family="quartz", supplier_id="supplier-a")
    b = SurfaceIdentity(canonical_name="Calacatta Gold", material_family="quartz", supplier_id="supplier-b")
    assert score_candidate_match(a, b) < 0.75


def test_same_supplier_and_sku_scores_as_a_strong_duplicate():
    a = SurfaceIdentity(
        canonical_name="Calacatta Gold", material_family="quartz", supplier_id="supplier-a", supplier_sku="SKU-1"
    )
    b = SurfaceIdentity(
        canonical_name="Calacatta Gold Quartz", material_family="quartz", supplier_id="supplier-a", supplier_sku="SKU-1"
    )
    assert score_candidate_match(a, b) >= 0.75


def test_different_material_family_is_never_a_duplicate_regardless_of_name():
    a = SurfaceIdentity(canonical_name="Carrara", material_family="quartz", supplier_id="supplier-a")
    b = SurfaceIdentity(canonical_name="Carrara", material_family="marble", supplier_id="supplier-a")
    assert score_candidate_match(a, b) == 0.0


def test_find_candidate_duplicates_returns_only_matches_above_threshold_sorted_desc():
    candidate = SurfaceIdentity(
        canonical_name="Nero Marquina", material_family="marble", manufacturer_id="mfr-1", brand_id="brand-1"
    )
    weak = SurfaceIdentity(canonical_name="Nero Marquina", material_family="marble")
    strong = SurfaceIdentity(
        canonical_name="Nero Marquina", material_family="marble", manufacturer_id="mfr-1", brand_id="brand-1"
    )
    results = find_candidate_duplicates(candidate, [("weak-id", weak), ("strong-id", strong)])
    assert [r[0] for r in results] == ["strong-id"]


# ---------------------------------------------------------------------------
# Task 8 — cost + margin precedence, never fabricated
# ---------------------------------------------------------------------------


def test_resolve_price_prefers_explicit_selling_price():
    override = TenantCatalogueOverride(
        buy_cost_per_slab=100, default_markup_percent=50, target_margin_percent=50, selling_price_per_slab=222
    )
    assert resolve_price_per_slab(override) == 222


def test_resolve_price_falls_back_to_markup():
    override = TenantCatalogueOverride(buy_cost_per_slab=100, default_markup_percent=50)
    assert resolve_price_per_slab(override) == 150.0


def test_resolve_price_falls_back_to_margin():
    override = TenantCatalogueOverride(buy_cost_per_slab=100, target_margin_percent=25)
    # 100 / (1 - 0.25) = 133.33
    assert resolve_price_per_slab(override) == 133.33


def test_resolve_price_is_none_when_nothing_is_set():
    override = TenantCatalogueOverride()
    assert resolve_price_per_slab(override) is None


def test_resolve_price_is_none_when_override_is_none():
    assert resolve_price_per_slab(None) is None


# ---------------------------------------------------------------------------
# Task 3 — tenant commercial overrides + isolation
# ---------------------------------------------------------------------------


def test_tenant_override_is_get_or_create_never_duplicated(db):
    tenant = _make_tenant(db, "OverrideUpsertTenant")
    surface = _seed_surface(db)
    try:
        first = crud.upsert_tenant_catalogue_override(
            db, tenant_id=tenant.id, surface_id=surface.id, surface_variant_id=None, buy_cost_per_slab=100
        )
        second = crud.upsert_tenant_catalogue_override(
            db, tenant_id=tenant.id, surface_id=surface.id, surface_variant_id=None, buy_cost_per_slab=150
        )
        assert first.id == second.id
        assert second.buy_cost_per_slab == 150
    finally:
        _cleanup_tenant(tenant.id, [surface.id])


def test_tenant_a_cannot_read_tenant_bs_private_surface(db):
    tenant_a = _make_tenant(db, "IsoTenantA")
    tenant_b = _make_tenant(db, "IsoTenantB")
    private_surface = _seed_surface(db, tenant_id=tenant_b.id, name="Tenant B Private Stone")
    try:
        assert crud.get_catalogue_surface_by_id(db, private_surface.id, tenant_a.id) is None
        assert crud.get_catalogue_surface_by_id(db, private_surface.id, tenant_b.id) is not None
        with pytest.raises(SurfaceNotFoundError):
            catalogue_service.get_detail(db, tenant_a.id, private_surface.id)
    finally:
        _cleanup_tenant(tenant_a.id)
        _cleanup_tenant(tenant_b.id, [private_surface.id])


def test_search_never_returns_another_tenants_private_surface(db):
    tenant_a = _make_tenant(db, "SearchIsoTenantA")
    tenant_b = _make_tenant(db, "SearchIsoTenantB")
    unique_name = f"UniquePrivateStone{uuid.uuid4().hex[:8]}"
    private_surface = _seed_surface(db, tenant_id=tenant_b.id, name=unique_name)
    try:
        results_a = catalogue_service.search(db, tenant_a.id, query=unique_name)
        assert private_surface.id not in [s.id for s in results_a]

        results_b = catalogue_service.search(db, tenant_b.id, query=unique_name)
        assert private_surface.id in [s.id for s in results_b]
    finally:
        _cleanup_tenant(tenant_a.id)
        _cleanup_tenant(tenant_b.id, [private_surface.id])


def test_tenant_b_cannot_see_tenant_as_price_override(client, db):
    tenant_a = _make_tenant(db, "PriceIsoTenantA")
    tenant_b = _make_tenant(db, "PriceIsoTenantB")
    surface = _seed_surface(db, name="Shared Global Surface For Price Isolation")
    try:
        crud.upsert_tenant_catalogue_override(
            db, tenant_id=tenant_a.id, surface_id=surface.id, surface_variant_id=None, selling_price_per_slab=999
        )
        assert crud.get_tenant_catalogue_override(db, tenant_b.id, surface.id, None) is None
        assert crud.get_tenant_catalogue_override(db, tenant_a.id, surface.id, None) is not None
    finally:
        _cleanup_tenant(tenant_a.id, [surface.id])
        _cleanup_tenant(tenant_b.id)


# ---------------------------------------------------------------------------
# HTTP surface — search, detail, override, custom materials
# ---------------------------------------------------------------------------


def test_search_surfaces_endpoint_filters_by_material_family(client, db):
    tenant = _make_tenant(db, "SearchHttpTenant")
    headers = _make_owner_headers(client, db, tenant, "search-http")
    quartz = _seed_surface(db, name=f"HttpSearchQuartz{uuid.uuid4().hex[:6]}", family="quartz")
    marble = _seed_surface(db, name=f"HttpSearchMarble{uuid.uuid4().hex[:6]}", family="marble")
    try:
        resp = client.get("/api/v1/catalogue/surfaces?material_family=quartz&limit=50", headers=headers)
        assert resp.status_code == 200, resp.text
        ids = [row["id"] for row in resp.json()]
        assert str(quartz.id) in ids
        assert str(marble.id) not in ids
    finally:
        _cleanup_tenant(tenant.id, [quartz.id, marble.id])


def test_get_surface_detail_distinguishes_global_and_tenant_data(client, db):
    tenant = _make_tenant(db, "DetailHttpTenant")
    headers = _make_owner_headers(client, db, tenant, "detail-http")
    surface = _seed_surface(db, name="Detail Endpoint Surface")
    _seed_variant(db, surface.id, thickness_mm=30.0)
    try:
        resp = client.get(f"/api/v1/catalogue/surfaces/{surface.id}", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["is_tenant_private"] is False
        assert body["tenant_override"] is None
        assert len(body["variants"]) == 1

        put = client.put(
            f"/api/v1/catalogue/surfaces/{surface.id}/override",
            json={"buy_cost_per_slab": 200, "default_markup_percent": 40},
            headers=headers,
        )
        assert put.status_code == 200, put.text
        assert put.json()["resolved_price_per_slab"] == 280.0

        resp2 = client.get(f"/api/v1/catalogue/surfaces/{surface.id}", headers=headers)
        assert resp2.json()["tenant_override"]["resolved_price_per_slab"] == 280.0
    finally:
        _cleanup_tenant(tenant.id, [surface.id])


def test_override_endpoint_requires_owner_role(client, db):
    tenant = _make_tenant(db, "OverrideRbacTenant")
    email = _unique_email("staff")
    auth_service.create_user(
        db, tenant_id=tenant.id, name="Pytest Staff", email=email, password=STRONG_PASSWORD, role="Staff"
    )
    login = client.post("/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD})
    staff_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    surface = _seed_surface(db, name="RBAC Override Surface")
    try:
        resp = client.put(
            f"/api/v1/catalogue/surfaces/{surface.id}/override",
            json={"buy_cost_per_slab": 100},
            headers=staff_headers,
        )
        assert resp.status_code == 403
    finally:
        _cleanup_tenant(tenant.id, [surface.id])


def test_custom_material_quote_only_creates_no_durable_row(client, db):
    tenant = _make_tenant(db, "CustomQuoteOnlyTenant")
    headers = _make_owner_headers(client, db, tenant, "custom-quote-only")
    try:
        resp = client.post(
            "/api/v1/catalogue/custom-materials",
            json={
                "canonical_name": "One-Off Reclaimed Slab",
                "material_family": "other_natural_stone",
                "buy_cost_per_slab": 300,
                "save_to_catalogue": False,
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["saved_to_catalogue"] is False
        assert body["surface_id"] is None

        remaining = (
            SessionLocal()
        )
        try:
            assert (
                remaining.query(CatalogueSurface)
                .filter(CatalogueSurface.canonical_name == "One-Off Reclaimed Slab")
                .count()
                == 0
            )
        finally:
            remaining.close()
    finally:
        _cleanup_tenant(tenant.id)


def test_custom_material_saved_to_catalogue_is_tenant_private_and_reusable(client, db):
    tenant = _make_tenant(db, "CustomSaveTenant")
    headers = _make_owner_headers(client, db, tenant, "custom-save")
    surface_id = None
    try:
        resp = client.post(
            "/api/v1/catalogue/custom-materials",
            json={
                "canonical_name": "Tenant Private Reusable Slab",
                "material_family": "granite",
                "variant": {"thickness_mm": 20, "finish": "Honed"},
                "buy_cost_per_slab": 250,
                "default_markup_percent": 30,
                "save_to_catalogue": True,
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["saved_to_catalogue"] is True
        surface_id = uuid.UUID(body["surface_id"])

        detail = client.get(f"/api/v1/catalogue/surfaces/{surface_id}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["is_tenant_private"] is True
        assert detail.json()["tenant_override"]["resolved_price_per_slab"] == 325.0
    finally:
        _cleanup_tenant(tenant.id, [surface_id] if surface_id else [])


# ---------------------------------------------------------------------------
# Task 6/7 — Stone Quote Engine V2: catalogue-driven quote creation +
# immutable snapshot
# ---------------------------------------------------------------------------


def _create_catalogue_quote(client, headers, surface_id, variant_id, *, customer_name):
    return client.post(
        "/api/v1/quote",
        json={
            "customer": customer_name,
            "postcode": "PYTESTCAT",
            "items": [
                {
                    "item_type": "worktop",
                    "material": "Snapshot Test Surface",
                    "thickness": "20mm",
                    "length_mm": 3000,
                    "width_mm": 650,
                    "catalogue_surface_id": str(surface_id),
                    "catalogue_variant_id": str(variant_id),
                }
            ],
        },
        headers=headers,
    )


def test_catalogue_quote_without_a_tenant_price_returns_400_not_a_fabricated_price(client, db):
    tenant = _make_tenant(db, "MissingPriceTenant")
    headers = _make_owner_headers(client, db, tenant, "missing-price")
    surface = _seed_surface(db, name="No Price Set Surface")
    variant = _seed_variant(db, surface.id)
    try:
        resp = _create_catalogue_quote(client, headers, surface.id, variant.id, customer_name="No Price Customer")
        assert resp.status_code == 400
        assert "No price is set" in resp.json()["detail"]
    finally:
        _cleanup_tenant(tenant.id, [surface.id])


def test_catalogue_quote_creates_an_immutable_snapshot_that_survives_later_catalogue_changes(client, db):
    tenant = _make_tenant(db, "SnapshotTenant")
    headers = _make_owner_headers(client, db, tenant, "snapshot")
    surface = _seed_surface(db, name="Original Surface Name")
    variant = _seed_variant(db, surface.id, thickness_mm=20.0)
    quote_id = None
    try:
        crud.upsert_tenant_catalogue_override(
            db,
            tenant_id=tenant.id,
            surface_id=surface.id,
            surface_variant_id=variant.id,
            selling_price_per_slab=500,
        )

        resp = _create_catalogue_quote(client, headers, surface.id, variant.id, customer_name="Snapshot Customer")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        quote_id = uuid.UUID(body["id"])
        original_line_total = body["items"][0]["line_total"]
        assert body["items"][0]["price_per_slab"] == 500

        # Now change the catalogue name AND the tenant's price — a real
        # "the catalogue/pricing changed later" scenario.
        surface.canonical_name = "Renamed Surface — Should Never Affect Old Quotes"
        db.add(surface)
        db.commit()
        crud.upsert_tenant_catalogue_override(
            db, tenant_id=tenant.id, surface_id=surface.id, surface_variant_id=variant.id, selling_price_per_slab=999
        )

        # Reopen the OLD quote's persisted row — its snapshot must be untouched.
        fresh = SessionLocal()
        try:
            item = fresh.query(QuoteItem).filter(QuoteItem.quote_id == quote_id).one()
            assert item.catalogue_snapshot["surface_name"] == "Original Surface Name"
            assert item.catalogue_snapshot["selling_price_used"] == 500
            assert item.price_per_slab == 500
            assert item.line_total == original_line_total
        finally:
            fresh.close()
    finally:
        if quote_id:
            db2 = SessionLocal()
            try:
                db2.execute(delete(QuoteItem).where(QuoteItem.quote_id == quote_id))
                db2.execute(delete(Quote).where(Quote.id == quote_id))
                db2.commit()
            finally:
                db2.close()
        _cleanup_tenant(tenant.id, [surface.id])


def test_catalogue_quote_from_a_different_tenants_private_surface_returns_400(client, db):
    tenant_a = _make_tenant(db, "CrossTenantQuoteA")
    tenant_b = _make_tenant(db, "CrossTenantQuoteB")
    headers_a = _make_owner_headers(client, db, tenant_a, "cross-quote-a")
    private_surface = _seed_surface(db, tenant_id=tenant_b.id, name="Tenant B Only Surface")
    try:
        resp = _create_catalogue_quote(
            client, headers_a, private_surface.id, uuid.uuid4(), customer_name="Cross Tenant Customer"
        )
        assert resp.status_code == 400
    finally:
        _cleanup_tenant(tenant_a.id)
        _cleanup_tenant(tenant_b.id, [private_surface.id])


# ---------------------------------------------------------------------------
# Task 13 — construction/general quoting is completely untouched
# ---------------------------------------------------------------------------


def test_general_construction_quote_never_touches_the_catalogue(client, db):
    """A bathroom/electrical/general-building quote line has no
    catalogue_surface_id at all — the calculator's stone/catalogue
    branch is never entered for these, by construction (line_kind is
    never "stone" for a general quote)."""
    tenant = _make_tenant(db, "ConstructionRegressionTenant")
    headers = _make_owner_headers(client, db, tenant, "construction-regression")
    try:
        resp = client.post(
            "/api/v1/quotes",
            json={
                "title": "Bathroom refit",
                "trade": "bathroom",
                "lines": [
                    {"line_kind": "labour", "description": "Strip out", "quantity": 2, "unit": "day", "unit_price": 250},
                    {"line_kind": "material", "description": "Tiles", "quantity": 20, "unit": "m2", "unit_price": 35},
                ],
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["quote_kind"] == "general"
        for item in body["items"]:
            assert item.get("catalogue_surface_id") is None
    finally:
        db2 = SessionLocal()
        try:
            quote_ids = [row[0] for row in db2.query(Quote.id).filter(Quote.tenant_id == tenant.id).all()]
            if quote_ids:
                db2.execute(delete(QuoteItem).where(QuoteItem.quote_id.in_(quote_ids)))
                db2.execute(delete(Quote).where(Quote.id.in_(quote_ids)))
                db2.commit()
        finally:
            db2.close()
        _cleanup_tenant(tenant.id)


# ---------------------------------------------------------------------------
# Task 17 — AI catalogue grounding never fabricates price/availability
# ---------------------------------------------------------------------------


def test_ai_catalogue_search_reports_missing_price_explicitly_never_fabricated(db):
    from app.catalogue.ai import search_for_ai

    tenant = _make_tenant(db, "AiGroundingTenant")
    surface = _seed_surface(db, name=f"AiGroundingSurface{uuid.uuid4().hex[:6]}")
    try:
        results = search_for_ai(db, tenant.id, surface.canonical_name)
        assert len(results) == 1
        assert results[0]["price_available"] is False
        assert results[0]["price_per_slab"] is None

        crud.upsert_tenant_catalogue_override(
            db, tenant_id=tenant.id, surface_id=surface.id, surface_variant_id=None, selling_price_per_slab=444
        )
        results2 = search_for_ai(db, tenant.id, surface.canonical_name)
        assert results2[0]["price_available"] is True
        assert results2[0]["price_per_slab"] == 444
    finally:
        _cleanup_tenant(tenant.id, [surface.id])

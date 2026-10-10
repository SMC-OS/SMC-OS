"""DEF019: approval/handoff must not discard stone layout and extras."""
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from app.quotes.service import QuoteService


def test_handoff_keeps_agreed_line_details_scope_and_exclusions_in_project():
    quote = SimpleNamespace(id=uuid.uuid4(), status="approved", customer_id=None, trade="stone",
        site_address_line1=None, site_address_line2=None, site_city=None, site_postcode=None, total=720,
        currency="GBP", scope_of_works="Template and fit synthetic kitchen", exclusions="No plumbing",
        terms="Synthetic deposit terms", notes="Internal fitting instruction",
        items=[SimpleNamespace(line_kind="stone", item_type="worktop", material="Quartz", thickness="20mm",
            quantity=1, length_mm=2400, width_mm=650, line_total=600,
            notes="Layout: Peninsula. Extras: Sink / hob cutout, Polished edge")])
    with patch("app.quotes.service.crud.get_quote_by_id", return_value=quote), \
         patch("app.quotes.service.crud.get_project_by_quote_id", return_value=None), \
         patch("app.quotes.service.resolve_initial_binding", return_value=(uuid.uuid4(), uuid.uuid4())), \
         patch("app.quotes.service.crud.create_project", return_value=SimpleNamespace(id=uuid.uuid4())) as create, \
         patch("app.quotes.service.activity_service.log"):
        QuoteService().handoff(MagicMock(), quote.id, uuid.uuid4())
    notes = create.call_args.kwargs["notes"]
    assert notes is not None
    for detail in ["Layout: Peninsula", "Sink / hob cutout", "Polished edge", "Quartz", "2400", "650",
                   "Template and fit synthetic kitchen", "No plumbing", "Synthetic deposit terms", "Internal fitting instruction"]:
        assert detail in notes


def test_handoff_persists_stone_layout_and_extras_through_http(client, auth_headers):
    from sqlalchemy import delete, select
    from app.database.database import SessionLocal
    from app.database.models import Quote, QuoteItem, Project
    quote_id = project_id = None
    response = client.post("/api/v1/quote", headers=auth_headers, json={
        "customer": "Synthetic handoff details", "items": [{"material": "Calacatta Gold", "thickness": "20mm",
            "item_type": "worktop", "length_mm": 2400, "width_mm": 650,
            "notes": "Layout: Peninsula. Extras: Sink / hob cutout, Polished edge"}]})
    assert response.status_code == 200, response.text
    quote_id = uuid.UUID(response.json()["id"])
    try:
        assert client.post(f"/api/v1/quotes/{quote_id}/approve", headers=auth_headers).status_code == 200
        handed_off = client.post(f"/api/v1/quotes/{quote_id}/handoff", headers=auth_headers)
        assert handed_off.status_code in (200, 201), handed_off.text
        project_id = uuid.UUID(handed_off.json()["id"])
        saved = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
        assert saved.status_code == 200
        for text in ["Layout: Peninsula", "Sink / hob cutout", "Polished edge", "2400", "650"]:
            assert text in saved.json()["notes"]
        again = client.post(f"/api/v1/quotes/{quote_id}/handoff", headers=auth_headers)
        assert again.json()["id"] == str(project_id)
        assert again.json()["notes"] == saved.json()["notes"]
    finally:
        with SessionLocal() as db:
            # Tenant-scoped HTTP handlers are the exercised behaviour; cleanup
            # only removes this test's freshly generated identifiers.
            if project_id:
                db.execute(delete(Project).where(Project.id == project_id))
            if quote_id:
                db.execute(delete(QuoteItem).where(QuoteItem.quote_id == quote_id))
                db.execute(delete(Quote).where(Quote.id == quote_id))
            db.commit()

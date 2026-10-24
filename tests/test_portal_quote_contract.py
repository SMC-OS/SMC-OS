"""Stone-Hard DEF008: public quotes support both persisted quote kinds."""
import uuid
from datetime import datetime, timezone

import pytest
from app.portal.models import PortalQuoteOut

@pytest.mark.parametrize("kind", ["stone", "general"])
def test_portal_quote_accepts_real_persisted_kind_without_internal_data(kind):
    values = {
        "id": uuid.uuid4(), "quote_kind": kind,
        "title": "Synthetic renovation", "currency": "EUR",
        "material": "Quartz" if kind == "stone" else None,
        "thickness": "20mm" if kind == "stone" else None,
        "kitchen_length": 3.0 if kind == "stone" else None,
        "price_before_vat": 100, "vat": 20, "total": 120,
        "created_at": datetime.now(timezone.utc),
        "tenant_id": uuid.uuid4(), "customer_id": uuid.uuid4(),
        "notes": "Internal margin detail", "scope_of_works": "Private draft",
    }
    public = PortalQuoteOut.model_validate(values).model_dump()
    assert public["quote_kind"] == kind
    assert public["currency"] == "EUR"
    assert public["title"] == "Synthetic renovation"
    assert public["material"] == values["material"]
    assert public["total"] == 120
    assert not ({"tenant_id", "customer_id", "notes", "scope_of_works"} & public.keys())

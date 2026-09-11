"""GeoCore AI drafting — Sprint 039, Workstream C.

The three things this feature must get right, in order of how badly each
would hurt if it were wrong:

  1. **AI never sends.** The drafting service has no delivery call, no
     `DeliveryService` import, and a return shape with no delivery field of
     any kind — so "the AI sent it" is structurally impossible rather than
     merely prohibited by instruction (§4 Decision 4).
  2. **Grounded only in tenant-authorised data.** Every entity a draft
     references is re-fetched with the caller's own `tenant_id`. Naming
     another tenant's quote gets a 404, never a cross-tenant read.
  3. **Sending is a separate, human act**, and goes through Sprint 038's
     `DeliveryService` and the existing communications ledger — never a
     second delivery path.

No test here calls a real language model. The drafting service takes an
injected client, exactly as `AIDraftService` (Sprint 027) and
`DeliveryService` (Sprint 038) already do.
"""

import uuid

import pytest
from sqlalchemy import delete, select

from app.ai import drafting
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Communication,
    Customer,
    EmailSuppression,
    NotificationRecord,
    Project,
    Quote,
    QuoteItem,
    Tenant,
    User,
)

RUN_ID = uuid.uuid4().hex[:8]
TENANT_NAME = f"Pytest AI Drafting {RUN_ID}"
OWNER_EMAIL = f"pytest-ai-drafting-{RUN_ID}@example.invalid"
OWNER_PASSWORD = "pytest-ai-drafting-password-1"


def _cleanup():
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        if tenant is not None:
            db.execute(delete(EmailSuppression).where(EmailSuppression.tenant_id == tenant.id))
            db.execute(delete(Communication).where(Communication.tenant_id == tenant.id))
            db.execute(
                delete(NotificationRecord).where(NotificationRecord.tenant_id == tenant.id)
            )
            db.execute(delete(Project).where(Project.tenant_id == tenant.id))
            quote_ids = select(Quote.id).where(Quote.tenant_id == tenant.id)
            db.execute(delete(QuoteItem).where(QuoteItem.quote_id.in_(quote_ids)))
            db.execute(delete(Quote).where(Quote.tenant_id == tenant.id))
            db.execute(delete(Customer).where(Customer.tenant_id == tenant.id))
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == tenant.id))
            db.execute(delete(User).where(User.tenant_id == tenant.id))
            db.execute(delete(Tenant).where(Tenant.id == tenant.id))
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _run_cleanup():
    _cleanup()
    yield
    _cleanup()


@pytest.fixture()
def workspace(client):
    r = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": TENANT_NAME,
            "name": "Drafting Owner",
            "email": OWNER_EMAIL,
            "password": OWNER_PASSWORD,
        },
    )
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    customer = client.post(
        "/api/v1/customers",
        json={"name": "Jane Okafor", "email": "jane@example.invalid"},
        headers=headers,
    )
    assert customer.status_code == 201, customer.text
    return headers, customer.json()


class _FakeClient:
    """Stands in for the OpenAI client. Records what it was asked and
    returns a fixed draft, so a test can assert on the *prompt* as well as
    the result — which is how the tenant-scoping guarantees below are
    actually checked."""

    def __init__(self, subject="A subject", body="A body."):
        self.calls: list[dict] = []
        self._subject = subject
        self._body = body

        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.calls.append(kwargs)
                return _FakeCompletion(outer._subject, outer._body)

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()

    @property
    def prompt_text(self) -> str:
        return "\n".join(
            message["content"]
            for call in self.calls
            for message in call.get("messages", [])
        )


class _FakeCompletion:
    def __init__(self, subject, body):
        self.choices = [
            type(
                "Choice",
                (),
                {
                    "message": type(
                        "Message",
                        (),
                        {"content": f"Subject: {subject}\n\n{body}"},
                    )()
                },
            )()
        ]


# --- Rule 1: the AI cannot send ------------------------------------------


def test_the_drafting_result_has_no_delivery_field_of_any_kind():
    """Structural, not instructional (§4 Decision 4). A response shape with
    nowhere to put "sent" cannot claim to have sent anything."""
    fields = set(drafting.DraftResult.model_fields)

    assert fields == {"kind", "subject", "body", "engine", "grounded_in"}
    for forbidden in ("sent", "delivered", "recipient", "communication_id", "status"):
        assert forbidden not in fields, forbidden


def test_the_drafting_module_never_imports_the_delivery_service():
    """The strongest available guarantee short of a type system: the module
    that writes customer text has no way to transmit it.

    Checked against the module's real import graph rather than its source
    text, so the docstring explaining *why* it cannot send does not fail
    the test proving it cannot.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(drafting))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)

    assert not any("communications" in name for name in imported), sorted(imported)


def test_drafting_creates_no_communication_row(client, workspace):
    headers, customer = workspace

    client.post(
        "/api/v1/ai/draft",
        json={"kind": "general", "customer_id": customer["id"]},
        headers=headers,
    )

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        assert (
            db.query(Communication).filter(Communication.tenant_id == tenant.id).count()
            == 0
        )
    finally:
        db.close()


# --- Rule 2: tenant-authorised data only ---------------------------------


def test_drafting_about_another_tenants_customer_returns_404(
    client, workspace, other_tenant_auth_headers
):
    """Naming an id you do not own must be indistinguishable from naming
    one that does not exist (ADR-029) — and must certainly not put that
    customer's details into a prompt."""
    headers, customer = workspace

    r = client.post(
        "/api/v1/ai/draft",
        json={"kind": "general", "customer_id": customer["id"]},
        headers=other_tenant_auth_headers,
    )

    assert r.status_code == 404


def test_drafting_about_an_unknown_customer_returns_404(client, workspace):
    headers, _ = workspace

    r = client.post(
        "/api/v1/ai/draft",
        json={"kind": "general", "customer_id": str(uuid.uuid4())},
        headers=headers,
    )

    assert r.status_code == 404


def test_drafting_about_another_tenants_quote_returns_404(
    client, workspace, other_tenant_auth_headers
):
    headers, customer = workspace
    quote = client.post(
        "/api/v1/quotes",
        json={
            "customer_id": customer["id"],
            "title": "Kitchen refit",
            "trade": "kitchen",
            "lines": [
                {"description": "Fitting", "quantity": 1, "unit": "item", "unit_price": 1200}
            ],
        },
        headers=headers,
    )
    assert quote.status_code == 201, quote.text

    r = client.post(
        "/api/v1/ai/draft",
        json={"kind": "quote_follow_up", "quote_id": quote.json()["id"]},
        headers=other_tenant_auth_headers,
    )

    assert r.status_code == 404


def test_the_prompt_only_ever_contains_this_tenants_own_records(
    client, workspace, other_tenant_auth_headers
):
    """The positive form of the rule: build a draft for our own customer
    while another tenant has a customer of its own, and prove nothing of
    theirs reached the prompt."""
    headers, customer = workspace
    other = client.post(
        "/api/v1/customers",
        json={"name": "Someone Else Entirely", "email": "other@example.invalid"},
        headers=other_tenant_auth_headers,
    )
    assert other.status_code == 201

    fake = _FakeClient()
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        service = drafting.AIDraftingService(client=fake)
        service.draft(
            db,
            tenant_id=tenant.id,
            request=drafting.DraftRequest(
                kind="general", customer_id=uuid.UUID(customer["id"])
            ),
        )
    finally:
        db.close()

    assert "Jane Okafor" in fake.prompt_text
    assert "Someone Else Entirely" not in fake.prompt_text


# --- What it produces -----------------------------------------------------


def test_every_supported_kind_is_one_the_brief_asked_for():
    assert set(drafting.DRAFT_KINDS) == {
        "quote_delivery",
        "quote_follow_up",
        "project_update",
        "appointment_update",
        "payment_reminder",
        "general",
    }


def test_an_unknown_kind_is_rejected(client, workspace):
    headers, customer = workspace

    r = client.post(
        "/api/v1/ai/draft",
        json={"kind": "ransom_note", "customer_id": customer["id"]},
        headers=headers,
    )

    assert r.status_code == 422


def test_a_draft_comes_back_with_a_subject_and_a_body(workspace):
    _, customer = workspace
    fake = _FakeClient(subject="About your kitchen", body="Hello Jane, ...")
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        result = drafting.AIDraftingService(client=fake).draft(
            db,
            tenant_id=tenant.id,
            request=drafting.DraftRequest(
                kind="general", customer_id=uuid.UUID(customer["id"])
            ),
        )

        assert result.subject == "About your kitchen"
        assert "Hello Jane" in result.body
        assert result.engine == "llm"
    finally:
        db.close()


def test_a_draft_says_what_it_was_grounded_in(workspace):
    """So a reviewer can see which records the model was shown before
    deciding whether to trust what it wrote."""
    _, customer = workspace
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        result = drafting.AIDraftingService(client=_FakeClient()).draft(
            db,
            tenant_id=tenant.id,
            request=drafting.DraftRequest(
                kind="general", customer_id=uuid.UUID(customer["id"])
            ),
        )

        assert any("Jane Okafor" in entry for entry in result.grounded_in)
    finally:
        db.close()


def test_rewriting_works_on_a_supplied_draft(workspace):
    _, customer = workspace
    fake = _FakeClient(subject="Shorter", body="Short version.")
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        result = drafting.AIDraftingService(client=fake).rewrite(
            db,
            tenant_id=tenant.id,
            request=drafting.RewriteRequest(
                subject="A long subject",
                body="A very long body that goes on and on.",
                instruction="shorten",
            ),
        )

        assert result.body == "Short version."
        assert "A very long body" in fake.prompt_text
    finally:
        db.close()


def test_an_unknown_rewrite_instruction_is_rejected(client, workspace):
    headers, _ = workspace

    r = client.post(
        "/api/v1/ai/rewrite",
        json={"subject": "x", "body": "y", "instruction": "translate to klingon"},
        headers=headers,
    )

    assert r.status_code == 422


# --- No LLM configured: honest, not fabricated ---------------------------


def test_with_no_llm_configured_drafting_reports_itself_unavailable(client, workspace):
    """It must not fall back to a canned template and present it as an AI
    draft — the Sprint 036 honesty rule, applied to generation."""
    headers, customer = workspace

    r = client.post(
        "/api/v1/ai/draft",
        json={"kind": "general", "customer_id": customer["id"]},
        headers=headers,
    )

    assert r.status_code == 503
    assert "no ai provider is connected" in r.json()["detail"].lower()


def test_capabilities_states_whether_drafting_is_available(client, workspace):
    headers, _ = workspace

    body = client.get("/api/v1/ai/capabilities", headers=headers).json()

    assert "drafting" in body
    assert body["drafting"] is False  # no OPENAI_API_KEY in this environment


# --- Rule 3: sending is a separate, human act ----------------------------


def test_a_reviewed_message_is_sent_through_the_existing_ledger(client, workspace):
    """The send endpoint writes a Communication exactly like every other
    Sprint 038 send — no second delivery architecture."""
    headers, customer = workspace

    r = client.post(
        "/api/v1/communications/send",
        json={
            "customer_id": customer["id"],
            "kind": "general",
            "subject": "About your kitchen",
            "body": "Hello Jane,\n\nJust a quick update.",
        },
        headers=headers,
    )

    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        rows = db.query(Communication).filter(Communication.tenant_id == tenant.id).all()
        assert len(rows) == 1
        assert rows[0].recipient == "jane@example.invalid"
        assert rows[0].subject == "About your kitchen"
    finally:
        db.close()


def test_a_message_can_only_be_sent_to_a_customer_of_your_own_tenant(
    client, workspace, other_tenant_auth_headers
):
    headers, customer = workspace

    r = client.post(
        "/api/v1/communications/send",
        json={
            "customer_id": customer["id"],
            "kind": "general",
            "subject": "x",
            "body": "y",
        },
        headers=other_tenant_auth_headers,
    )

    assert r.status_code == 404


def test_a_message_is_never_sent_to_a_free_text_address(client, workspace):
    """The recipient is always resolved from a customer record the caller
    owns. There is no field for an arbitrary address, which is what stops
    this being a general-purpose mailer."""
    from app.communications.models import CustomerMessageRequest

    assert "recipient" not in CustomerMessageRequest.model_fields
    assert "to" not in CustomerMessageRequest.model_fields


def test_sending_to_a_customer_with_no_email_is_refused(client, workspace):
    headers, _ = workspace
    no_email = client.post(
        "/api/v1/customers", json={"name": "No Email Ltd"}, headers=headers
    )
    assert no_email.status_code == 201

    r = client.post(
        "/api/v1/communications/send",
        json={
            "customer_id": no_email.json()["id"],
            "kind": "general",
            "subject": "x",
            "body": "y",
        },
        headers=headers,
    )

    assert r.status_code == 422


def test_the_same_reviewed_message_is_never_sent_twice(client, workspace):
    """A double-clicked Send must not produce two emails. The client passes
    an idempotency key it generated when the compose panel opened, so the
    second click resolves to the same communication."""
    headers, customer = workspace
    key = f"pytest-idem-{uuid.uuid4().hex}"
    payload = {
        "customer_id": customer["id"],
        "kind": "general",
        "subject": "About your kitchen",
        "body": "Hello Jane,",
        "idempotency_key": key,
    }

    first = client.post("/api/v1/communications/send", json=payload, headers=headers)
    second = client.post("/api/v1/communications/send", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == TENANT_NAME).first()
        assert (
            db.query(Communication).filter(Communication.tenant_id == tenant.id).count()
            == 1
        )
    finally:
        db.close()


def test_sending_requires_authentication(client):
    r = client.post(
        "/api/v1/communications/send",
        json={"customer_id": str(uuid.uuid4()), "kind": "general", "subject": "x", "body": "y"},
    )

    assert r.status_code in (401, 403)

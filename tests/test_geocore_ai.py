"""GeoCore AI — Sprint 036, Workstream H.

The sprint contract's hard constraint for this workstream is honesty: do
not create fake AI capabilities. That produces three things worth testing:

  * the capability endpoint tells the truth about this deployment;
  * with no AI provider configured, the assistant still works and says
    which engine answered rather than passing a keyword matcher off as AI;
  * with one configured, the workspace context sent to the model contains
    business facts and no customer contact details.
"""

import uuid

import pytest

from app.ai import context as ai_context
from app.ai.models import ChatMessage
from app.ai.service import AIService
from app.ai.providers import LLMProvider, LLMResponse, LLMProviderError
from app.core.config import settings

RUN_ID = uuid.uuid4().hex[:8]


class _StubProvider(LLMProvider):
    """Stub LLM provider for testing."""

    def __init__(self, content="Two quotes need chasing.", fail=False):
        self.content = content
        self.fail = fail
        self.sent = None

    @property
    def name(self) -> str:
        return "stub"

    @property
    def is_configured(self) -> bool:
        return True

    @property
    def model(self) -> str:
        return "stub-model"

    def chat(self, messages: list[dict[str, str]]) -> LLMResponse:
        if self.fail:
            raise LLMProviderError("provider unreachable", self.name)
        self.sent = messages
        return LLMResponse(content=self.content)

    def chat_structured(self, messages: list[dict[str, str]], response_format: type):
        raise NotImplementedError("Structured output not needed for chat tests")


def test_capabilities_are_honest_when_no_provider_is_configured(client, auth_headers):
    r = client.get("/api/v1/ai/capabilities", headers=auth_headers)
    assert r.status_code == 200
    caps = r.json()

    assert caps["llm_configured"] is bool(settings.openai_api_key)
    if not settings.openai_api_key:
        # The interface must not advertise what isn't connected.
        assert caps["workspace_context"] is False
        assert caps["quote_drafting"] is False
        assert any("built-in" in note for note in caps["notes"])
    # The built-in catalogue assistant works either way, so this is always
    # true — and it is the thing the fallback actually offers.
    assert caps["material_search"] is True


def test_chat_answers_and_names_the_engine(client, auth_headers):
    r = client.post(
        "/api/v1/ai/chat",
        json={"messages": [{"role": "user", "content": "What does 20mm quartz cost?"}]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["reply"]
    assert body["engine"] in {"llm", "builtin"}


def test_chat_never_leaks_developer_internals(client, auth_headers):
    r = client.post(
        "/api/v1/ai/chat",
        json={"messages": [{"role": "user", "content": "hello"}]},
        headers=auth_headers,
    ).json()

    # The old AI Assistant page named POST /process, BrainManager and a
    # sprint number in its own product copy. Nothing GeoCore AI returns
    # may do that again.
    lowered = r["reply"].lower()
    for leak in ("brainmanager", "/process", "sprint", "endpoint", "traceback"):
        assert leak not in lowered


@pytest.mark.parametrize(
    "payload",
    [
        {"messages": []},
        {"messages": [{"role": "user", "content": ""}]},
        {"messages": [{"role": "user", "content": "x"}] * 25},
    ],
)
def test_rejects_malformed_conversations(client, auth_headers, payload):
    r = client.post("/api/v1/ai/chat", json=payload, headers=auth_headers)
    assert r.status_code == 422


def test_requires_authentication(client):
    r = client.post(
        "/api/v1/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]}
    )
    assert r.status_code == 401


def test_uses_the_llm_when_one_is_available(db, auth_headers, client):
    stub = _StubProvider(content="Three quotes are waiting on the customer.")
    service = AIService(provider=stub)
    tenant_id = uuid.UUID(client.get("/api/v1/auth/me", headers=auth_headers).json()["tenant_id"])

    response = service.chat(db, tenant_id, [ChatMessage(content="What needs my attention?")])

    assert response.engine == "llm"
    assert response.reply == "Three quotes are waiting on the customer."
    assert stub.sent is not None


def test_falls_back_honestly_when_the_provider_is_unreachable(db, auth_headers, client):
    service = AIService(provider=_StubProvider(fail=True))
    tenant_id = uuid.UUID(client.get("/api/v1/auth/me", headers=auth_headers).json()["tenant_id"])

    response = service.chat(db, tenant_id, [ChatMessage(content="What needs my attention?")])

    # A provider outage must not leave the user with an error page for a
    # question the built-in path could answer — and the reply must say so
    # rather than passing the fallback off as the AI.
    assert response.engine == "builtin"
    assert "couldn't reach" in response.reply.lower()


def test_the_prompt_is_grounded_and_carries_no_contact_details(db, auth_headers, client):
    stub = _StubProvider()
    service = AIService(provider=stub)
    me = client.get("/api/v1/auth/me", headers=auth_headers).json()
    tenant_id = uuid.UUID(me["tenant_id"])

    customer = client.post(
        "/api/v1/customers",
        json={
            "name": f"Pytest AI {RUN_ID}",
            "email": f"ai-{RUN_ID}@example.invalid",
            "phone": "07123 999888",
            "address_line1": "1 Secret Lane",
        },
        headers=auth_headers,
    ).json()

    service.chat(db, tenant_id, [ChatMessage(content="What needs my attention?")])
    prompt = " ".join(m["content"] for m in stub.sent)

    # Grounded in real workspace facts...
    assert "Workspace summary" in prompt
    assert "customers" in prompt
    # ...but personal contact details have no business leaving the
    # database to answer "how many quotes are outstanding".
    assert customer["email"] not in prompt
    assert "07123 999888" not in prompt
    assert "1 Secret Lane" not in prompt


def test_the_prompt_does_not_claim_geocore_cannot_email_customers(db, auth_headers, client):
    # Sprint 039 Production Readiness Defect Gate, Blocker 4: the prompt
    # used to say "GeoCore cannot send email, SMS or messages to
    # customers", which stopped being true once Sprint 038 shipped quote
    # delivery and follow-up automation. It must never tell a user their
    # own product can't do something it does every day.
    stub = _StubProvider()
    service = AIService(provider=stub)
    tenant_id = uuid.UUID(client.get("/api/v1/auth/me", headers=auth_headers).json()["tenant_id"])

    service.chat(db, tenant_id, [ChatMessage(content="Can GeoCore email my customer?")])
    system_prompt = stub.sent[0]["content"]

    assert "cannot send email" not in system_prompt.lower()
    assert "geocore itself can email a customer" in system_prompt.lower()


def test_context_is_bounded_and_tenant_scoped(db, auth_headers, client):
    tenant_id = uuid.UUID(client.get("/api/v1/auth/me", headers=auth_headers).json()["tenant_id"])
    summary = ai_context.build(db, tenant_id)

    assert set(summary) >= {"customers", "quotes", "projects", "open_tasks"}
    # Bounded: headline lists never grow with the size of the workspace.
    assert len(summary["recent_quote_titles"]) <= 5
    assert len(summary["recent_project_names"]) <= 5
    assert len(summary["open_task_titles"]) <= 5
    # A quote total is a price offered, never revenue — the key name says
    # so, so a model cannot read it as income.
    assert "quoted_value_recent" in summary["quotes"]
    assert "revenue" not in str(summary)

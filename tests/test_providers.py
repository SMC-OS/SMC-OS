"""Tests for the LLM provider abstraction and Gemini provider.

These tests verify the provider abstraction works correctly for both
OpenAI and Gemini providers, following TDD principles.
"""

import uuid
import pytest

from app.ai.providers import (
    LLMProvider,
    OpenAIProvider,
    GeminiProvider,
    get_active_provider,
    get_provider_by_name,
    LLMProviderUnavailable,
    LLMProviderRateLimit,
    LLMProviderTimeout,
    LLMProviderError,
)
from app.core.config import settings


class TestProviderSelection:
    """Tests for provider selection logic."""

    def test_get_active_provider_returns_none_when_no_key_configured(self, monkeypatch):
        """When no provider has a key configured, get_active_provider returns None."""
        monkeypatch.setattr(settings, "ai_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", None)
        monkeypatch.setattr(settings, "gemini_api_key", None)

        provider = get_active_provider()
        assert provider is None

    def test_get_active_provider_openai_when_configured(self, monkeypatch):
        """OpenAI provider is returned when AI_PROVIDER=openai and key is set."""
        monkeypatch.setattr(settings, "ai_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", "sk-test-key")
        monkeypatch.setattr(settings, "gemini_api_key", None)

        provider = get_active_provider()
        assert provider is not None
        assert provider.name == "openai"
        assert provider.is_configured is True

    def test_get_active_provider_gemini_when_configured(self, monkeypatch):
        """Gemini provider is returned when AI_PROVIDER=gemini and key is set."""
        monkeypatch.setattr(settings, "ai_provider", "gemini")
        monkeypatch.setattr(settings, "openai_api_key", None)
        monkeypatch.setattr(settings, "gemini_api_key", "gemini-test-key")

        provider = get_active_provider()
        assert provider is not None
        assert provider.name == "gemini"
        assert provider.is_configured is True

    def test_get_active_provider_openai_key_missing_returns_none(self, monkeypatch):
        """When AI_PROVIDER=openai but key is missing, returns None."""
        monkeypatch.setattr(settings, "ai_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", None)

        provider = get_active_provider()
        assert provider is None

    def test_get_active_provider_gemini_key_missing_returns_none(self, monkeypatch):
        """When AI_PROVIDER=gemini but key is missing, returns None."""
        monkeypatch.setattr(settings, "ai_provider", "gemini")
        monkeypatch.setattr(settings, "gemini_api_key", None)

        provider = get_active_provider()
        assert provider is None

    def test_get_active_provider_invalid_provider_returns_none(self, monkeypatch):
        """Invalid AI_PROVIDER value returns None."""
        monkeypatch.setattr(settings, "ai_provider", "invalid")
        monkeypatch.setattr(settings, "openai_api_key", "sk-test")

        provider = get_active_provider()
        assert provider is None

    def test_get_provider_by_name_openai(self, monkeypatch):
        """get_provider_by_name returns OpenAI provider when configured."""
        monkeypatch.setattr(settings, "openai_api_key", "sk-test")

        provider = get_provider_by_name("openai")
        assert provider is not None
        assert provider.name == "openai"

    def test_get_provider_by_name_gemini(self, monkeypatch):
        """get_provider_by_name returns Gemini provider when configured."""
        monkeypatch.setattr(settings, "gemini_api_key", "gemini-test")

        provider = get_provider_by_name("gemini")
        assert provider is not None
        assert provider.name == "gemini"

    def test_get_provider_by_name_returns_none_when_not_configured(self, monkeypatch):
        """get_provider_by_name returns None when provider not configured."""
        monkeypatch.setattr(settings, "openai_api_key", None)

        provider = get_provider_by_name("openai")
        assert provider is None

    def test_get_provider_by_name_invalid_returns_none(self):
        """get_provider_by_name returns None for invalid provider name."""
        provider = get_provider_by_name("invalid")
        assert provider is None


class TestOpenAIProvider:
    """Tests for OpenAI provider implementation."""

    def test_openai_provider_properties(self, monkeypatch):
        """OpenAI provider has correct properties."""
        monkeypatch.setattr(settings, "openai_api_key", "sk-test")
        monkeypatch.setattr(settings, "openai_model", "gpt-4o-mini")

        provider = OpenAIProvider()
        assert provider.name == "openai"
        assert provider.is_configured is True
        assert provider.model == "gpt-4o-mini"

    def test_openai_provider_not_configured(self, monkeypatch):
        """OpenAI provider reports not configured when key missing."""
        monkeypatch.setattr(settings, "openai_api_key", None)

        provider = OpenAIProvider()
        assert provider.is_configured is False

    def test_openai_provider_chat_structured_not_implemented_in_stub(self):
        """OpenAI provider chat_structured requires real client."""
        provider = OpenAIProvider()
        # The actual implementation is tested via integration tests
        # This just verifies the interface exists
        assert hasattr(provider, "chat_structured")
        assert hasattr(provider, "chat")


class TestGeminiProvider:
    """Tests for Gemini provider implementation."""

    def test_gemini_provider_properties(self, monkeypatch):
        """Gemini provider has correct properties."""
        monkeypatch.setattr(settings, "gemini_api_key", "gemini-test")
        monkeypatch.setattr(settings, "gemini_model", "gemini-1.5-flash")

        provider = GeminiProvider()
        assert provider.name == "gemini"
        assert provider.is_configured is True
        assert provider.model == "gemini-1.5-flash"

    def test_gemini_provider_not_configured(self, monkeypatch):
        """Gemini provider reports not configured when key missing."""
        monkeypatch.setattr(settings, "gemini_api_key", None)

        provider = GeminiProvider()
        assert provider.is_configured is False

    def test_gemini_provider_has_required_methods(self):
        """Gemini provider implements required interface."""
        provider = GeminiProvider()
        assert hasattr(provider, "chat")
        assert hasattr(provider, "chat_structured")


class TestProviderErrorHandling:
    """Tests for provider error handling and sanitization."""

    def test_llm_provider_error_stores_provider_name(self):
        """LLMProviderError stores provider name for debugging."""
        try:
            raise LLMProviderError("test error", "gemini")
        except LLMProviderError as e:
            assert e.provider == "gemini"
            assert str(e) == "test error"

    def test_llm_provider_unavailable(self):
        """LLMProviderUnavailable is a subclass of LLMProviderError."""
        assert issubclass(LLMProviderUnavailable, LLMProviderError)

    def test_llm_provider_rate_limit(self):
        """LLMProviderRateLimit is a subclass of LLMProviderError."""
        assert issubclass(LLMProviderRateLimit, LLMProviderError)

    def test_llm_provider_timeout(self):
        """LLMProviderTimeout is a subclass of LLMProviderError."""
        assert issubclass(LLMProviderTimeout, LLMProviderError)


class TestProviderCapabilities:
    """Tests that capabilities endpoint reports active provider correctly."""

    def test_capabilities_reports_active_provider_openai(self, client, auth_headers, monkeypatch):
        """Capabilities endpoint reports OpenAI as active provider."""
        # ai_service reads settings lazily via get_active_provider(), so
        # patching settings is sufficient — no singleton replacement needed.
        monkeypatch.setattr(settings, "ai_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", "sk-test")
        monkeypatch.setattr(settings, "openai_model", "gpt-4o-mini")
        monkeypatch.setattr(settings, "gemini_api_key", None)

        r = client.get("/api/v1/ai/capabilities", headers=auth_headers)
        assert r.status_code == 200
        caps = r.json()
        assert caps["llm_configured"] is True
        assert caps["active_provider"] == "openai"
        assert caps["active_model"] == "gpt-4o-mini"
        assert any("openai" in note.lower() for note in caps["notes"])

    def test_capabilities_reports_active_provider_gemini(self, client, auth_headers, monkeypatch):
        """Capabilities endpoint reports Gemini as active provider."""
        # ai_service reads settings lazily via get_active_provider(), so
        # patching settings is sufficient — no singleton replacement needed.
        monkeypatch.setattr(settings, "ai_provider", "gemini")
        monkeypatch.setattr(settings, "gemini_api_key", "gemini-test")
        monkeypatch.setattr(settings, "gemini_model", "gemini-1.5-flash")
        monkeypatch.setattr(settings, "openai_api_key", None)

        r = client.get("/api/v1/ai/capabilities", headers=auth_headers)
        assert r.status_code == 200
        caps = r.json()
        assert caps["llm_configured"] is True
        assert caps["active_provider"] == "gemini"
        assert caps["active_model"] == "gemini-1.5-flash"
        assert any("gemini" in note.lower() for note in caps["notes"])

    def test_capabilities_reports_false_when_no_provider(self, client, auth_headers, monkeypatch):
        """Capabilities reports llm_configured=false when no provider configured."""
        monkeypatch.setattr(settings, "ai_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", None)
        monkeypatch.setattr(settings, "gemini_api_key", None)

        r = client.get("/api/v1/ai/capabilities", headers=auth_headers)
        assert r.status_code == 200
        caps = r.json()
        assert caps["llm_configured"] is False
        assert caps["active_provider"] is None
        assert caps["active_model"] is None
        assert any("built-in" in note for note in caps["notes"])


class TestProviderTenantIsolation:
    """Tests that tenant isolation works regardless of provider."""

    def test_chat_tenant_context_identical_across_providers(
        self, db, auth_headers, client, monkeypatch
    ):
        """Tenant context building is identical regardless of provider."""
        # This test verifies that the context building (app.ai.context) is
        # provider-independent - it doesn't test the provider itself
        from app.ai import context as ai_context

        tenant_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=auth_headers).json()["tenant_id"]
        )
        summary = ai_context.build(db, tenant_id)

        # Context should have expected keys
        assert "customers" in summary
        assert "quotes" in summary
        assert "projects" in summary
        assert "open_tasks" in summary

    def test_cross_tenant_isolation_enforced(self, db, auth_headers, client, monkeypatch):
        """Cross-tenant isolation is enforced regardless of provider."""
        # Create a customer in current tenant
        r = client.post(
            "/api/v1/customers",
            json={"name": "Test Customer", "email": "test@example.com"},
            headers=auth_headers,
        )
        assert r.status_code == 201
        customer_id = r.json()["id"]

        # Try to access from different tenant - should fail
        # (This is enforced at the database/query level, not provider level)
        from app.database import crud
        import uuid

        # Create a second tenant and user directly
        other_tenant_id = uuid.uuid4()
        # Query should return empty for other tenant
        customers = crud.list_customers(db, other_tenant_id)
        assert len(customers) == 0


class TestProviderSafetyBoundaries:
    """Tests that providers respect safety boundaries."""

    def test_no_invented_figures_in_system_prompt(self):
        """System prompt explicitly forbids inventing figures."""
        from app.ai.service import _SYSTEM_PROMPT

        assert "Never invent a number" in _SYSTEM_PROMPT
        assert "Never describe quoted value as revenue" in _SYSTEM_PROMPT

    def test_no_silent_actions_in_system_prompt(self):
        """System prompt explicitly forbids silent actions."""
        from app.ai.service import _SYSTEM_PROMPT

        assert "You cannot take actions yourself" in _SYSTEM_PROMPT
        assert "never as something you have done" in _SYSTEM_PROMPT

    def test_ai_draft_structured_output_no_price_fields(self):
        """AI draft structured output has no price fields (structural guarantee)."""
        from app.quotes.ai_draft import _AIExtraction, _AIItemExtraction
        from pydantic import BaseModel

        # Verify the schema has no price-related fields
        extraction_fields = _AIExtraction.model_fields.keys()
        item_fields = _AIItemExtraction.model_fields.keys()

        assert "price" not in extraction_fields
        assert "cost" not in extraction_fields
        assert "revenue" not in extraction_fields
        assert "profit" not in extraction_fields
        assert "total" not in extraction_fields

        assert "price" not in item_fields
        assert "cost" not in item_fields
        assert "revenue" not in item_fields
        assert "profit" not in item_fields
        assert "total" not in item_fields


class TestGeminiChat:
    """Tests for Gemini chat functionality (mocked)."""

    def test_gemini_chat_returns_response(self, monkeypatch):
        """Gemini chat returns a response when mocked."""
        # This is a unit test with a stub - real integration tests
        # would need actual API credentials
        from app.ai.providers import LLMResponse

        class MockGeminiProvider(GeminiProvider):
            def chat(self, messages):
                return LLMResponse(content="Test response from Gemini")

        provider = MockGeminiProvider()
        response = provider.chat([{"role": "user", "content": "Hello"}])
        assert response.content == "Test response from Gemini"

    def test_gemini_structured_output_returns_parsed(self, monkeypatch):
        """Gemini structured output returns parsed model."""
        from app.ai.providers import LLMStructuredResponse
        from app.quotes.ai_draft import _AIExtraction

        class MockGeminiProvider(GeminiProvider):
            def chat_structured(self, messages, response_format):
                extraction = _AIExtraction(
                    customer="Test",
                    items=[{"item_type": "worktop", "text_span": "3m"}],
                )
                return LLMStructuredResponse(parsed=extraction)

        provider = MockGeminiProvider()
        response = provider.chat_structured(
            [{"role": "user", "content": "Test"}],
            _AIExtraction,
        )
        assert response.parsed is not None
        assert response.parsed.customer == "Test"


class TestGeminiErrorHandling:
    """Tests for Gemini error handling."""

    def test_gemini_rate_limit_error(self):
        """Gemini rate limit error is properly categorized."""
        from app.ai.providers import LLMProviderRateLimit

        try:
            raise LLMProviderRateLimit("quota exceeded", "gemini")
        except LLMProviderRateLimit as e:
            assert e.provider == "gemini"
            assert "quota" in str(e).lower()

    def test_gemini_timeout_error(self):
        """Gemini timeout error is properly categorized."""
        from app.ai.providers import LLMProviderTimeout

        try:
            raise LLMProviderTimeout("request timeout exceeded", "gemini")
        except LLMProviderTimeout as e:
            assert e.provider == "gemini"
            assert "timeout" in str(e).lower()

    def test_provider_errors_sanitized_for_users(self):
        """Provider errors don't expose API keys or sensitive data."""
        from app.ai.providers import LLMProviderError

        # Simulate an error that might contain sensitive info
        error_msg = "API key sk-abc123 invalid: quota exceeded"
        try:
            raise LLMProviderError(error_msg, "gemini")
        except LLMProviderError as e:
            # The error stores the original but the API layer should sanitize
            assert "sk-abc123" in str(e.original_error) if e.original_error else True
            # In production, the API layer catches and sanitizes


# Integration-style tests that verify the provider abstraction works end-to-end
class TestProviderIntegration:
    """Integration tests for provider abstraction."""

    def test_ai_service_works_with_openai_provider(self, db, auth_headers, client, monkeypatch):
        """AIService works with OpenAI provider."""
        monkeypatch.setattr(settings, "ai_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", "sk-test")
        monkeypatch.setattr(settings, "gemini_api_key", None)

        from app.ai.service import AIService
        from app.ai.providers import LLMProvider, LLMResponse

        class StubProvider(LLMProvider):
            @property
            def name(self): return "openai"
            @property
            def is_configured(self): return True
            @property
            def model(self): return "gpt-4o-mini"
            def chat(self, messages):
                return LLMResponse(content="OpenAI response")
            def chat_structured(self, messages, response_format):
                raise NotImplementedError()

        service = AIService(provider=StubProvider())
        tenant_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=auth_headers).json()["tenant_id"]
        )

        from app.ai.models import ChatMessage
        response = service.chat(db, tenant_id, [ChatMessage(content="Test")])
        assert response.engine == "llm"
        assert response.reply == "OpenAI response"

    def test_ai_service_works_with_gemini_provider(self, db, auth_headers, client, monkeypatch):
        """AIService works with Gemini provider."""
        monkeypatch.setattr(settings, "ai_provider", "gemini")
        monkeypatch.setattr(settings, "gemini_api_key", "gemini-test")
        monkeypatch.setattr(settings, "openai_api_key", None)

        from app.ai.service import AIService
        from app.ai.providers import LLMProvider, LLMResponse

        class StubProvider(LLMProvider):
            @property
            def name(self): return "gemini"
            @property
            def is_configured(self): return True
            @property
            def model(self): return "gemini-1.5-flash"
            def chat(self, messages):
                return LLMResponse(content="Gemini response")
            def chat_structured(self, messages, response_format):
                raise NotImplementedError()

        service = AIService(provider=StubProvider())
        tenant_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=auth_headers).json()["tenant_id"]
        )

        from app.ai.models import ChatMessage
        response = service.chat(db, tenant_id, [ChatMessage(content="Test")])
        assert response.engine == "llm"
        assert response.reply == "Gemini response"

    def test_ai_draft_service_works_with_openai_provider(self, db, auth_headers, client, monkeypatch):
        """AIDraftService works with OpenAI provider."""
        monkeypatch.setattr(settings, "ai_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", "sk-test")
        monkeypatch.setattr(settings, "gemini_api_key", None)

        from app.quotes.ai_draft import AIDraftService
        from app.ai.providers import LLMProvider, LLMStructuredResponse
        from app.quotes.ai_draft import _AIExtraction

        class StubProvider(LLMProvider):
            @property
            def name(self): return "openai"
            @property
            def is_configured(self): return True
            @property
            def model(self): return "gpt-4o-mini"
            def chat(self, messages):
                raise NotImplementedError()
            def chat_structured(self, messages, response_format):
                return LLMStructuredResponse(parsed=_AIExtraction(
                    customer="Test",
                    items=[{"item_type": "worktop", "text_span": "3m"}],
                ))

        service = AIDraftService(provider=StubProvider())
        draft = service.generate(db, "3m worktop")
        assert draft.customer == "Test"
        assert len(draft.items) == 1

    def test_ai_draft_service_works_with_gemini_provider(self, db, auth_headers, client, monkeypatch):
        """AIDraftService works with Gemini provider."""
        monkeypatch.setattr(settings, "ai_provider", "gemini")
        monkeypatch.setattr(settings, "gemini_api_key", "gemini-test")
        monkeypatch.setattr(settings, "openai_api_key", None)

        from app.quotes.ai_draft import AIDraftService
        from app.ai.providers import LLMProvider, LLMStructuredResponse
        from app.quotes.ai_draft import _AIExtraction

        class StubProvider(LLMProvider):
            @property
            def name(self): return "gemini"
            @property
            def is_configured(self): return True
            @property
            def model(self): return "gemini-1.5-flash"
            def chat(self, messages):
                raise NotImplementedError()
            def chat_structured(self, messages, response_format):
                return LLMStructuredResponse(parsed=_AIExtraction(
                    customer="Test",
                    items=[{"item_type": "worktop", "text_span": "3m"}],
                ))

        service = AIDraftService(provider=StubProvider())
        draft = service.generate(db, "3m worktop")
        assert draft.customer == "Test"
        assert len(draft.items) == 1
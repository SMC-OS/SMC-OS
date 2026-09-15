"""LLM Provider abstraction for GeoCore AI.

This module defines the provider interface and implementations for different
LLM providers (OpenAI, Gemini). The abstraction ensures application/business
logic does not depend directly on provider-specific SDK types.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, NoReturn

from app.core.config import settings


@dataclass
class LLMResponse:
    """Standardized response from an LLM provider."""
    content: str
    raw_response: Any = None


@dataclass
class LLMStructuredResponse:
    """Standardized structured response from an LLM provider."""
    parsed: Any
    raw_response: Any = None


class LLMProviderError(Exception):
    """Base exception for LLM provider errors."""
    def __init__(self, message: str, provider: str, original_error: Exception | None = None):
        super().__init__(message)
        self.provider = provider
        self.original_error = original_error


class LLMProviderUnavailable(LLMProviderError):
    """Raised when the provider is not configured."""
    pass


class LLMProviderTimeout(LLMProviderError):
    """Raised when the provider request times out."""
    pass


class LLMProviderRateLimit(LLMProviderError):
    """Raised when the provider returns a rate limit/quota error."""
    pass


class LLMProviderInvalidResponse(LLMProviderError):
    """Raised when the provider returns an invalid/malformed response."""
    pass


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g., 'openai', 'gemini')."""
        pass

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Whether this provider has valid configuration."""
        pass

    @property
    @abstractmethod
    def model(self) -> str:
        """The model name being used."""
        pass

    @abstractmethod
    def chat(self, messages: list[dict[str, str]]) -> LLMResponse:
        """Send a chat completion request."""
        pass

    @abstractmethod
    def chat_structured(
        self, messages: list[dict[str, str]], response_format: type
    ) -> LLMStructuredResponse:
        """Send a structured chat completion request."""
        pass


class OpenAIProvider(LLMProvider):
    """OpenAI API provider implementation."""

    def __init__(self, client=None) -> None:
        self._client = client

    @property
    def name(self) -> str:
        return "openai"

    @property
    def is_configured(self) -> bool:
        return bool(settings.openai_api_key)

    @property
    def model(self) -> str:
        return settings.openai_model

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not settings.openai_api_key:
            raise LLMProviderUnavailable("OpenAI API key not configured", self.name)
        from openai import OpenAI
        self._client = OpenAI(api_key=settings.openai_api_key)
        return self._client

    def chat(self, messages: list[dict[str, str]]) -> LLMResponse:
        try:
            client = self._get_client()
            completion = client.chat.completions.create(
                model=self.model,
                messages=messages,
            )
            content = (completion.choices[0].message.content or "").strip()
            return LLMResponse(content=content, raw_response=completion)
        except LLMProviderError:
            raise
        except Exception as exc:
            self._handle_error(exc)

    def chat_structured(
        self, messages: list[dict[str, str]], response_format: type
    ) -> LLMStructuredResponse:
        try:
            client = self._get_client()
            completion = client.chat.completions.parse(
                model=self.model,
                messages=messages,
                response_format=response_format,
            )
            choice = completion.choices[0]
            if getattr(choice.message, "refusal", None):
                raise LLMProviderInvalidResponse(
                    "The model declined to process this request.", self.name
                )
            parsed = choice.message.parsed
            if parsed is None:
                raise LLMProviderInvalidResponse(
                    "The model did not return a parseable response.", self.name
                )
            return LLMStructuredResponse(parsed=parsed, raw_response=completion)
        except LLMProviderError:
            raise
        except Exception as exc:
            self._handle_error(exc)

    def _handle_error(self, exc: Exception) -> NoReturn:
        """Convert provider exceptions to standardized LLMProviderError."""
        error_str = str(exc).lower()
        if "rate_limit" in error_str or "quota" in error_str or "429" in error_str:
            raise LLMProviderRateLimit(str(exc), self.name, exc) from exc
        if "timeout" in error_str or "timed out" in error_str:
            raise LLMProviderTimeout(str(exc), self.name, exc) from exc
        raise LLMProviderError(str(exc), self.name, exc) from exc


class GeminiProvider(LLMProvider):
    """Google Gemini API provider implementation."""

    def __init__(self, client=None) -> None:
        self._client = client

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def is_configured(self) -> bool:
        return bool(settings.gemini_api_key)

    @property
    def model(self) -> str:
        return settings.gemini_model

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not settings.gemini_api_key:
            raise LLMProviderUnavailable("Gemini API key not configured", self.name)
        from google import genai
        self._client = genai.Client(api_key=settings.gemini_api_key)
        return self._client

    def chat(self, messages: list[dict[str, str]]) -> LLMResponse:
        try:
            client = self._get_client()
            # Convert messages to Gemini format
            contents = []
            for msg in messages:
                role = msg["role"]
                content = msg["content"]
                if role == "system":
                    # Gemini uses system_instruction separately
                    continue
                contents.append({"role": role, "parts": [{"text": content}]})

            # Extract system instruction if present
            system_instruction = None
            for msg in messages:
                if msg["role"] == "system":
                    system_instruction = msg["content"]
                    break

            response = client.models.generate_content(
                model=self.model,
                contents=contents,
                config={"system_instruction": system_instruction} if system_instruction else None,
            )
            content = (response.text or "").strip()
            return LLMResponse(content=content, raw_response=response)
        except LLMProviderError:
            raise
        except Exception as exc:
            self._handle_error(exc)

    def chat_structured(
        self, messages: list[dict[str, str]], response_format: type
    ) -> LLMStructuredResponse:
        try:
            client = self._get_client()
            contents = []
            for msg in messages:
                role = msg["role"]
                content = msg["content"]
                if role == "system":
                    continue
                contents.append({"role": role, "parts": [{"text": content}]})

            system_instruction = None
            for msg in messages:
                if msg["role"] == "system":
                    system_instruction = msg["content"]
                    break

            # Structured output per official docs: response_mime_type +
            # response_schema, then validate the JSON text into the Pydantic
            # model (mirrors docs' model_json_schema/model_validate_json).
            from google.genai import types

            schema = response_format.model_json_schema()
            response = client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=schema,
                ),
            )
            # Parse the JSON response into the Pydantic model
            parsed = response_format.model_validate_json(response.text)
            return LLMStructuredResponse(parsed=parsed, raw_response=response)
        except LLMProviderError:
            raise
        except Exception as exc:
            self._handle_error(exc)

    def _handle_error(self, exc: Exception) -> NoReturn:
        """Convert provider exceptions to standardized LLMProviderError."""
        error_str = str(exc).lower()
        if "rate_limit" in error_str or "quota" in error_str or "429" in error_str:
            raise LLMProviderRateLimit(str(exc), self.name, exc) from exc
        if "timeout" in error_str or "timed out" in error_str:
            raise LLMProviderTimeout(str(exc), self.name, exc) from exc
        raise LLMProviderError(str(exc), self.name, exc) from exc


def get_active_provider() -> LLMProvider | None:
    """Get the active LLM provider based on configuration."""
    provider_name = settings.ai_provider.lower()
    if provider_name == "openai":
        provider = OpenAIProvider()
        return provider if provider.is_configured else None
    elif provider_name == "gemini":
        provider = GeminiProvider()
        return provider if provider.is_configured else None
    return None


def get_provider_by_name(name: str) -> LLMProvider | None:
    """Get a specific provider by name if configured."""
    name = name.lower()
    if name == "openai":
        provider = OpenAIProvider()
        return provider if provider.is_configured else None
    elif name == "gemini":
        provider = GeminiProvider()
        return provider if provider.is_configured else None
    return None
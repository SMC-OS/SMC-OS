from pydantic import BaseModel, Field

# Bounded so one request cannot carry an unbounded conversation into a
# paid LLM call, and so the context this service builds stays the dominant
# part of the prompt rather than being pushed out by history.
MAX_MESSAGES = 20
MAX_MESSAGE_CHARS = 4000

ROLES = {"user", "assistant"}


class ChatMessage(BaseModel):
    role: str = "user"
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatRequest(BaseModel):
    """A conversation turn.

    History is supplied by the client rather than persisted server-side.
    That is a deliberate v1 boundary, stated here rather than left
    ambiguous: GeoCore AI holds no conversation table yet, so a
    conversation lives for as long as the tab does. Persisting it is a
    real feature (search, sharing, audit) and is listed as follow-up work
    rather than half-built.
    """

    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_MESSAGES)


class ChatResponse(BaseModel):
    reply: str
    # Which engine actually answered — "llm" when a real model was called,
    # "builtin" when the deterministic keyword assistant did. Surfaced to
    # the UI so it can be honest about what the user is talking to, rather
    # than presenting a keyword matcher as an AI.
    engine: str
    # Present only for a builtin answer that came from a catalogue lookup,
    # so the UI can show what was actually found rather than paraphrasing.
    data: dict | list | None = None


class AICapabilities(BaseModel):
    """What GeoCore AI can genuinely do in this deployment.

    Served so the UI never has to guess, and never advertises a capability
    that isn't configured. Every flag here reflects real backend state, not
    a roadmap.
    """

    conversational: bool
    llm_configured: bool
    workspace_context: bool
    quote_drafting: bool
    material_search: bool
    notes: list[str]
    # Active provider information (when llm_configured is true)
    active_provider: str | None = None
    active_model: str | None = None

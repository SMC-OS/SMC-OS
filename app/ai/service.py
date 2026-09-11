"""GeoCore AI — the conversational assistant (Sprint 036, Workstream H).

**What this is honest about.**

GeoCore has two genuinely different things that have both been called
"AI", and Sprint 036's contract is not to blur them:

  * A real LLM, used by app/quotes/ai_draft.py, available only when
    OPENAI_API_KEY is configured. When it is configured, this service uses
    it, grounded in a bounded, tenant-scoped summary of the workspace.

  * app/brain/BrainManager — a *keyword* router over the material
    catalogue and a pricing reply. Not a language model. Useful, fast, and
    deterministic; not an assistant.

When no key is configured, this service falls back to BrainManager and
says so: the response carries `engine: "builtin"`, and the UI renders that
as the built-in assistant rather than as AI. It does not pretend, and it
does not fail — a workspace with no LLM configured still gets a working
material lookup instead of an error page.

**What it will not do.** It has no tools and cannot write. It cannot
create a quote, change a price, send anything, or modify any record. Every
answer is text. That is a v1 boundary chosen deliberately — a
write-capable assistant needs a permission model, a confirmation step and
an audit trail, and shipping it without those would be the kind of feature
that has to be switched off a week later.
"""

import uuid

from sqlalchemy.orm import Session

from app.ai import context as ai_context
from app.ai.models import AICapabilities, ChatMessage, ChatResponse
from app.brain.manager import BrainManager
from app.core.config import settings

_SYSTEM_PROMPT = (
    "You are GeoCore AI, the assistant inside GeoCore — an operating "
    "system for construction and renovation businesses. The people you "
    "help run building, renovation, extension, kitchen, bathroom, "
    "roofing, flooring, decorating, plumbing, electrical, carpentry and "
    "stone/worktop businesses. Stone and worktops are one specialism "
    "among many, never the assumed default.\n\n"
    "You are given a short factual summary of this workspace. Use it. "
    "Never invent a number, a customer, a quote, a project or a price "
    "that is not in that summary — if you do not have the figure, say so "
    "and say where in GeoCore to find it.\n\n"
    # Sprint 039 corrected this. The previous wording said "GeoCore cannot
    # send email, SMS or messages to customers", which stopped being true
    # the moment Sprint 038 shipped — so the assistant was telling people
    # their own product could not do something it does.
    "You cannot take actions. You cannot create, edit, send or delete "
    "anything yourself. GeoCore *can* email customers — it can send a "
    "quote, and it can draft a message for someone to review and send — "
    "but every message that reaches a customer is sent by a person who "
    "read it first, never by you. If asked to do something, explain what "
    "the person should do in GeoCore instead of implying you have done "
    "it.\n\n"
    "A quote total is a price offered or committed to, never revenue or "
    "income. Never describe quoted value as revenue.\n\n"
    "Answer in British English, use GBP unless told otherwise, and be "
    "brief and practical — this is someone on a job, not in a meeting."
)


class AIService:
    def __init__(self, client=None) -> None:
        # Injectable for tests, exactly like AIDraftService. Nothing here
        # touches the OpenAI SDK at import or startup time.
        self._client = client
        self._brain = BrainManager()

    @property
    def llm_configured(self) -> bool:
        return bool(self._client is not None or settings.openai_api_key)

    def capabilities(self) -> AICapabilities:
        configured = self.llm_configured
        notes = [
            "GeoCore AI answers questions and drafts messages. It never "
            "sends anything — you read every draft and send it yourself.",
        ]
        if not configured:
            notes.append(
                "No AI provider is connected to this workspace, so GeoCore AI "
                "is answering with its built-in catalogue assistant. Ask about "
                "a material or a price to see what it can do."
            )
        return AICapabilities(
            conversational=True,
            llm_configured=configured,
            workspace_context=configured,
            quote_drafting=configured,
            material_search=True,
            drafting=configured,
            notes=notes,
        )

    def _get_client(self):
        if self._client is not None:
            return self._client
        from openai import OpenAI  # imported lazily — never at startup

        self._client = OpenAI(api_key=settings.openai_api_key)
        return self._client

    def chat(
        self, db: Session, tenant_id: uuid.UUID, messages: list[ChatMessage]
    ) -> ChatResponse:
        if not self.llm_configured:
            return self._builtin_reply(db, messages)

        summary = ai_context.build(db, tenant_id)
        payload = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "system",
                "content": f"Workspace summary (facts you may rely on): {summary}",
            },
        ]
        payload += [
            {"role": m.role if m.role in {"user", "assistant"} else "user", "content": m.content}
            for m in messages
        ]

        try:
            completion = self._get_client().chat.completions.create(
                model=settings.openai_model,
                messages=payload,
            )
            reply = (completion.choices[0].message.content or "").strip()
        except Exception:  # noqa: BLE001 — network/timeout/API errors of any shape
            # A provider outage must not leave the user with nothing. Fall
            # back to the deterministic assistant and label the answer
            # honestly, rather than returning a 502 for a question the
            # built-in path could have answered.
            return self._builtin_reply(db, messages, degraded=True)

        if not reply:
            return self._builtin_reply(db, messages, degraded=True)
        return ChatResponse(reply=reply, engine="llm")

    def _builtin_reply(
        self, db: Session, messages: list[ChatMessage], degraded: bool = False
    ) -> ChatResponse:
        """The deterministic path: app/brain's keyword router over the real
        material catalogue. It genuinely answers material and price
        questions; it genuinely cannot hold a conversation, and the reply
        says so rather than producing something conversational-sounding
        that isn't."""
        latest = next(
            (m.content for m in reversed(messages) if m.role == "user"), ""
        )
        result = self._brain.process(db, latest)

        prefix = (
            "I couldn't reach the AI service just now, so this is GeoCore's "
            "built-in assistant. "
            if degraded
            else ""
        )

        status = result.get("status") if isinstance(result, dict) else None
        if isinstance(result, dict) and result.get("reply"):
            return ChatResponse(
                reply=prefix + str(result["reply"]), engine="builtin", data=result
            )
        if status == "found":
            return ChatResponse(
                reply=prefix + "Here's what I found in your material catalogue.",
                engine="builtin",
                data=result,
            )

        return ChatResponse(
            reply=(
                prefix
                + "I'm GeoCore's built-in assistant. I can look up materials "
                "and prices from your catalogue — try “What does 20mm quartz "
                "cost?” or “Show me marble”. For full conversational "
                "answers about your quotes, projects and jobs, an AI provider "
                "needs to be connected to this workspace."
            ),
            engine="builtin",
            data=result if isinstance(result, (dict, list)) else None,
        )


ai_service = AIService()

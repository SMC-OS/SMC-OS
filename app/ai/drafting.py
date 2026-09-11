"""GeoCore AI drafting — writing a customer message, and nothing else
(Sprint 039, Workstream C).

**This module cannot send.** There is no delivery import here, no
`DeliveryService`, and `DraftResult` has no field that could hold a
delivery outcome. That is deliberate and structural (sprint-039.md §4
Decision 4): a response shape with nowhere to put "sent" cannot claim to
have sent anything, which is a far stronger guarantee than a system
prompt asking a model not to. Sending happens when a person reads the
draft, decides, and presses a button — and goes through Sprint 038's
`DeliveryService` and the existing communications ledger, never a second
delivery path.

**It is grounded only in tenant-authorised data.** Every entity a draft
references is re-fetched with the caller's own `tenant_id`, so naming
another tenant's quote produces a 404 rather than a cross-tenant read.
The context this builds is deliberately narrow — the customer's name, the
title and state of the one quote or project being written about, the
business's own name. Not a workspace dump, and never another customer's
details.

The trust posture follows `app/quotes/ai_draft.py` rather than
`app/ai/service.py`'s chat: bounded input, a lazily-constructed client,
no tools, and everything the model produces treated as *language* to be
reviewed by a human — never as an instruction, a number, or an action.
"""

import uuid
from dataclasses import dataclass

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import crud
from app.projects import pipeline_config

#: What a draft can be about. Each maps to a `CommunicationType` when a
#: human eventually sends it — see app/communications/models.py.
DRAFT_KINDS: tuple[str, ...] = (
    "quote_delivery",
    "quote_follow_up",
    "project_update",
    "appointment_update",
    "payment_reminder",
    "general",
)

#: What the model may be asked to do to an existing draft. A closed set,
#: because "instruction" is otherwise a free-text channel into a prompt.
REWRITE_INSTRUCTIONS: tuple[str, ...] = (
    "shorten",
    "expand",
    "warmer",
    "more_formal",
    "simpler",
)

#: Tones a draft can be written in. Also closed, for the same reason.
TONES: tuple[str, ...] = ("friendly", "professional", "direct")

MAX_NOTES_CHARS = 500
MAX_BODY_CHARS = 8000


class DraftingUnavailableError(Exception):
    """Raised when no language model is configured.

    Deliberately an error rather than a canned-template fallback: a
    hand-written template presented as an AI draft would be exactly the
    kind of quiet dishonesty Sprint 036 refused for the chat assistant,
    and a person reviewing a draft deserves to know what wrote it.
    """


class EntityNotFoundError(Exception):
    """A referenced record does not belong to the caller's tenant — or does
    not exist. The caller cannot tell which, which is the point
    (ADR-029)."""


class DraftRequest(BaseModel):
    kind: str
    customer_id: uuid.UUID | None = None
    quote_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    tone: str = "friendly"
    #: Free text from the user — what they want the message to say. Bounded
    #: and never treated as an instruction to the *system*, only as
    #: content guidance inside the user turn.
    notes: str | None = Field(default=None, max_length=MAX_NOTES_CHARS)

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        if value not in DRAFT_KINDS:
            raise ValueError(f"kind must be one of {sorted(DRAFT_KINDS)}")
        return value

    @field_validator("tone")
    @classmethod
    def _known_tone(cls, value: str) -> str:
        if value not in TONES:
            raise ValueError(f"tone must be one of {sorted(TONES)}")
        return value


class RewriteRequest(BaseModel):
    subject: str = Field(max_length=300)
    body: str = Field(max_length=MAX_BODY_CHARS)
    instruction: str

    @field_validator("instruction")
    @classmethod
    def _known_instruction(cls, value: str) -> str:
        if value not in REWRITE_INSTRUCTIONS:
            raise ValueError(f"instruction must be one of {sorted(REWRITE_INSTRUCTIONS)}")
        return value


class DraftResult(BaseModel):
    """What drafting returns. Note what is *not* here.

    No `sent`, no `recipient`, no `communication_id`, no `status`. A
    caller cannot mistake this for something that happened, and a future
    edit cannot quietly add a send by filling in a field that already
    exists.

    `grounded_in` lists, in plain language, the records the model was
    shown — so a reviewer can judge whether to trust what it wrote rather
    than guessing what it knew.
    """

    kind: str
    subject: str
    body: str
    #: Always "llm". There is no non-LLM drafting path — see
    #: DraftingUnavailableError.
    engine: str
    grounded_in: list[str]


@dataclass(frozen=True)
class _Context:
    """The narrow, tenant-scoped facts a draft is built from."""

    tenant_name: str
    lines: list[str]
    grounded_in: list[str]


_SYSTEM_PROMPT = (
    "You are GeoCore AI, drafting a message from a construction or "
    "renovation business to one of its own customers.\n\n"
    "You are writing a DRAFT. A person at the business will read it, "
    "change whatever they want, and decide whether to send it. You are "
    "not sending anything and must never imply that you have.\n\n"
    "Use only the facts given to you below. Never invent a price, a date, "
    "a measurement, a person or a commitment that is not there. If "
    "something a message would normally mention is missing, leave a short "
    "obvious gap like [date] for the person to fill in rather than "
    "guessing — a guessed date in a customer's inbox is worse than a "
    "blank one.\n\n"
    "Write in British English. Be warm, plain and brief: this is a "
    "builder writing to a customer, not a marketing department. No "
    "slogans, no exclamation marks, no 'we are thrilled'. Sign off with "
    "the business name.\n\n"
    "Reply in exactly this format and nothing else:\n"
    "Subject: <one line>\n"
    "<blank line>\n"
    "<the message body>"
)

_KIND_BRIEF = {
    "quote_delivery": "Send the customer their quote and invite them to look at it and ask anything.",
    "quote_follow_up": "Politely follow up on a quote they have not answered yet. Do not pressure them.",
    "project_update": "Tell the customer how their job is going and what happens next.",
    "appointment_update": "Confirm or change a visit. Be specific about what is agreed and what is not.",
    "payment_reminder": "Remind the customer about an outstanding payment. Be courteous and matter-of-fact, never threatening.",
    "general": "Write the message the person has described below.",
}


class AIDraftingService:
    def __init__(self, client=None) -> None:
        # Injectable for tests, exactly like AIDraftService and
        # DeliveryService. Nothing here touches the OpenAI SDK at import
        # or startup time.
        self._client = client

    @property
    def available(self) -> bool:
        return bool(self._client is not None or settings.openai_api_key)

    def _get_client(self):
        if self._client is not None:
            return self._client
        from openai import OpenAI  # imported lazily — never at startup

        self._client = OpenAI(api_key=settings.openai_api_key)
        return self._client

    # --- Context, tenant-scoped by construction -------------------------

    def _context(self, db: Session, tenant_id: uuid.UUID, request: DraftRequest) -> _Context:
        """Gather the few facts this draft needs.

        Every lookup passes `tenant_id`. A record the caller does not own
        raises `EntityNotFoundError`, which the router turns into a 404 —
        so an id belonging to another tenant is never read, let alone put
        in a prompt.
        """
        tenant = crud.get_tenant_by_id(db, tenant_id)
        tenant_name = tenant.name if tenant is not None else ""
        lines: list[str] = [f"The business: {tenant_name}"]
        grounded: list[str] = []

        customer_id = request.customer_id

        quote = None
        if request.quote_id is not None:
            quote = crud.get_quote_by_id(db, request.quote_id, tenant_id)
            if quote is None:
                raise EntityNotFoundError("quote")
            customer_id = customer_id or quote.customer_id

        project = None
        if request.project_id is not None:
            project = crud.get_project_by_id(db, request.project_id, tenant_id)
            if project is None:
                raise EntityNotFoundError("project")
            customer_id = customer_id or project.customer_id

        customer = None
        if customer_id is not None:
            customer = crud.get_customer_by_id(db, customer_id, tenant_id)
            if customer is None:
                raise EntityNotFoundError("customer")

        if customer is not None:
            lines.append(f"The customer: {customer.name}")
            grounded.append(f"Customer: {customer.name}")

        if quote is not None:
            # The quote's *total* is included because a quote message is
            # meaningless without it — but it is stated as an offered
            # price, never as revenue, the same distinction Sprint 025
            # locked in and app/ai/context.py restates.
            lines.append(
                f"The quote: {quote.title or 'untitled'} — "
                f"{quote.currency} {quote.total:.2f} offered, currently {quote.status}"
            )
            if quote.valid_until is not None:
                lines.append(f"The quote is valid until {quote.valid_until.isoformat()}")
            grounded.append(f"Quote: {quote.title or 'untitled'}")

        if project is not None:
            pipeline = pipeline_config.resolve(db, tenant_id)
            stage = pipeline.get(project.status)
            lines.append(
                f"The job: {project.name} — currently at the "
                f"'{stage.label if stage else project.status}' stage"
            )
            if project.start_date is not None:
                lines.append(f"The job is due to start on {project.start_date.isoformat()}")
            if project.target_completion_date is not None:
                lines.append(
                    f"The job is targeted to finish on "
                    f"{project.target_completion_date.isoformat()}"
                )
            grounded.append(f"Project: {project.name}")

        return _Context(tenant_name=tenant_name, lines=lines, grounded_in=grounded)

    # --- The two operations ---------------------------------------------

    def draft(
        self, db: Session, *, tenant_id: uuid.UUID, request: DraftRequest
    ) -> DraftResult:
        # Authorisation first, capability second. Whether this workspace
        # has an AI provider connected has no bearing on whether the
        # caller may see a record, and an id belonging to another tenant
        # must answer "not found" either way.
        context = self._context(db, tenant_id, request)

        if not self.available:
            raise DraftingUnavailableError()

        user_lines = [_KIND_BRIEF[request.kind], "", "Facts you may rely on:"]
        user_lines += [f"- {line}" for line in context.lines]
        user_lines += ["", f"Tone: {request.tone}."]
        if request.notes:
            # The user's own words, clearly fenced as content rather than
            # as an instruction to the system.
            user_lines += ["", "What the person wants said:", request.notes]

        reply = self._complete(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": "\n".join(user_lines)},
            ]
        )
        subject, body = _split_reply(reply)
        return DraftResult(
            kind=request.kind,
            subject=subject,
            body=body,
            engine="llm",
            grounded_in=context.grounded_in,
        )

    def rewrite(
        self, db: Session, *, tenant_id: uuid.UUID, request: RewriteRequest
    ) -> DraftResult:
        """Change an existing draft without changing what it says.

        Takes the draft as input rather than regenerating from context, so
        a person's own edits survive a "make it shorter" — which is the
        whole reason this is a separate operation.
        """
        if not self.available:
            raise DraftingUnavailableError()

        instruction = {
            "shorten": "Make this shorter. Keep every fact and commitment it contains.",
            "expand": "Add a little more detail and warmth. Invent no new facts.",
            "warmer": "Make the tone warmer and more personal. Change no facts.",
            "more_formal": "Make the tone more formal. Change no facts.",
            "simpler": "Use plainer, simpler language. Change no facts.",
        }[request.instruction]

        reply = self._complete(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"{instruction}\n\n"
                        f"Subject: {request.subject}\n\n{request.body}"
                    ),
                },
            ]
        )
        subject, body = _split_reply(reply)
        return DraftResult(
            kind="general",
            subject=subject or request.subject,
            body=body,
            engine="llm",
            grounded_in=["The draft you supplied"],
        )

    def _complete(self, messages: list[dict]) -> str:
        """One model call.

        A provider failure raises rather than falling back: unlike the
        chat assistant, there is no deterministic path that could produce
        a comparable answer, and returning a template dressed as an AI
        draft would be worse than returning nothing.
        """
        try:
            completion = self._get_client().chat.completions.create(
                model=settings.openai_model,
                messages=messages,
            )
            return (completion.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001 — network/timeout/API errors
            raise DraftingUnavailableError(str(exc)) from exc


def _split_reply(reply: str) -> tuple[str, str]:
    """Pull the subject line off the model's reply.

    Tolerant on purpose: a model that ignores the format still produces
    usable text, and a draft is going to be read and edited by a person
    anyway. A reply with no recognisable subject line becomes an empty
    subject and a full body, which the reviewer can fix in two seconds —
    far better than a 500.
    """
    text = (reply or "").strip()
    if not text:
        return "", ""

    lines = text.splitlines()
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0].split(":", 1)[1].strip()
        body = "\n".join(lines[1:]).strip()
        return subject, body
    return "", text


ai_drafting_service = AIDraftingService()

"""Core SQLAlchemy models for GeoCore.

Sprint 002 — see docs/DATABASE_SCHEMA.md §2 for the source pydantic models
and informal shapes these are drawn from, and docs/DECISIONS.md ADR-013 for
why every table below carries a `tenant_id` column that isn't enforced yet.

Sprint 008 added the `Tenant` table itself and converted every `tenant_id`
column from a bare nullable UUID into a real `ForeignKey("tenants.id")` —
still nullable, still unenforced by any query. See ADR-025. Enforcement
(every query filtering by the caller's tenant) is Sprint 012, not this one.

These are the first real database models in the project. Columns are a
starting point, not a finalised schema — revisit foreign keys, indexes, and
constraints as each dependent module (CRM, Projects, Materials, Auth) is
actually built in its own sprint. No API routes read or write these tables
yet except activity_log/notifications (see app/activity, app/notifications).
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.database import Base


class Tenant(Base):
    """A company/workspace using GeoCore. Sprint 008 — schema only, no
    enforcement: the 7 tables below gain a real FK to this table but every
    existing row (and every query in every existing module) is untouched.
    See docs/DECISIONS.md ADR-025 for the full reasoning and what's
    deliberately deferred to Sprint 009 (tenant-aware auth) and Sprint 012
    (isolation enforcement).
    """

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="active")

    # Sprint 034 — customer-facing company identity. `name` above is the
    # workspace label staff see inside the product; the columns below are
    # what this tenant's own customers see on a quote/invoice PDF. All
    # nullable: an unconfigured tenant falls back to `name` (see
    # app/tenants/identity.py), never to another tenant's details and never
    # to the platform's own brand.
    legal_name: Mapped[str | None] = mapped_column(String, nullable=True)
    trading_name: Mapped[str | None] = mapped_column(String, nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String, nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    postcode: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String, nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String, nullable=True)
    website: Mapped[str | None] = mapped_column(String, nullable=True)
    company_number: Mapped[str | None] = mapped_column(String, nullable=True)
    vat_number: Mapped[str | None] = mapped_column(String, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    document_footer: Mapped[str | None] = mapped_column(String, nullable=True)

    # Sprint 036 — workspace configuration.
    #
    # `currency` is the single source of truth for how this tenant's money
    # is displayed and what a new quote is denominated in. It is mirrored
    # onto each Quote at creation so a historical document never silently
    # re-prices if the tenant later changes it. NOT NULL with a 'GBP'
    # server default: every existing tenant is a UK business today, and a
    # currency-less tenant would have no defensible display format.
    #
    # `trades` is a comma-separated list of the trade keys this business
    # selected during onboarding (see app/tenants/trades.py). Deliberately
    # a delimited String, not a JSON/ARRAY column: it is read whole, never
    # queried into, and this schema has no other JSON column to be
    # consistent with. NULL means "never asked", which is different from
    # "" ("asked, selected nothing").
    #
    # `logo_storage_filename` is the generated UUID-based filename of an
    # uploaded logo under UPLOAD_DIR (never a user-supplied path — same
    # path-traversal-safe-by-construction rule as Document, ADR-032). It
    # is separate from the pre-existing `logo_url`, which stays the
    # externally-hosted-URL escape hatch; identity resolution prefers the
    # uploaded file when both are set.
    currency: Mapped[str] = mapped_column(String, nullable=False, server_default="GBP")
    trades: Mapped[str | None] = mapped_column(String, nullable=True)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    logo_storage_filename: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Sprint 012 — indexed: every query is now filtered by tenant_id (ADR-029).
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)

    # Sprint 036 (Workstream D) — a construction customer record. Every
    # column below is nullable or defaulted, so every customer created
    # before this sprint stays valid with no backfill and the existing
    # CustomerCreate/{name,email,phone} request body keeps working
    # byte-for-byte.
    #
    # `customer_type` is "individual" | "company", plain String validated
    # at the Pydantic boundary (same no-native-enum convention as
    # Project.status). `company_name` is meaningful only for a company
    # customer; `name` stays the person you actually deal with either way,
    # which is why it remains the required field rather than being
    # replaced by a company name.
    customer_type: Mapped[str] = mapped_column(
        String, nullable=False, server_default="individual"
    )
    company_name: Mapped[str | None] = mapped_column(String, nullable=True)
    address_line1: Mapped[str | None] = mapped_column(String, nullable=True)
    address_line2: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    postcode: Mapped[str | None] = mapped_column(String, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Sprint 012 — indexed: every query is now filtered by tenant_id (ADR-029).
    # Stays nullable: POST /api/v1/quote and /estimate remain deliberately
    # public (ADR-023) — an anonymous quote is created with tenant_id=NULL
    # and is visible to no tenant's authenticated browsing routes.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True
    )

    # Sprint 033 (Workstream C) — these scalar columns are no longer the
    # source of truth for a quote's contents; `QuoteItem` rows (below)
    # are. They're kept, and still populated on every new quote, as a
    # best-effort single-item *summary* (the first item's material/
    # dimensions, or "Multiple materials"/"Mixed" when items disagree)
    # purely so existing readers that only ever knew a single-job quote
    # (the customer portal summary, dashboards, anything not yet updated
    # to read `items`) keep working without modification. See
    # QuoteService._summarize_items() for exactly how these are derived.
    # Sprint 036 (Workstream E) — GeoCore is construction & renovation
    # software, not worktop software. `quote_kind` discriminates a
    # "general" construction quote (priced from line items with unit
    # prices) from a "stone" quote (priced by the slab calculator). NOT
    # NULL with a 'stone' server default: every quote that existed before
    # this sprint *is* a stone quote, so the default states a fact rather
    # than guessing one.
    #
    # The five stone columns immediately below became nullable in the same
    # migration. A general quote genuinely has no slab material, thickness
    # or run length — writing a sentinel like "N/A" into a NOT NULL column
    # would be lying in the schema to avoid changing it. Existing rows
    # keep every value they had; nothing is rewritten.
    quote_kind: Mapped[str] = mapped_column(String, nullable=False, server_default="stone")

    material: Mapped[str | None] = mapped_column(String, nullable=True)
    thickness: Mapped[str | None] = mapped_column(String, nullable=True)
    # Sprint 032 (Workstream C) — kitchen_length (metres) is kept as a
    # derived/mirrored column for backward compatibility with existing
    # rows/reports; length_mm is now the source of truth for every new
    # quote (see app/quotes/service.py). Never write one without the
    # other — QuoteService keeps them in sync.
    kitchen_length: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    length_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    width_mm: Mapped[float] = mapped_column(Float, nullable=False, server_default="650")
    thickness_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    # What unit the caller originally entered dimensions in ("mm"/"cm"/
    # "m") — provenance only, canonical storage is always length_mm/
    # width_mm/thickness_mm in millimetres.
    unit_input: Mapped[str] = mapped_column(String, nullable=False, server_default="mm")
    island: Mapped[bool] = mapped_column(Boolean, default=False)
    waterfall: Mapped[int] = mapped_column(Integer, default=0)
    splashback: Mapped[bool] = mapped_column(Boolean, default=False)
    # Independent linear dimensions — Sprint 032 fixes the bug where a
    # splashback/upstand silently reused the worktop run's own length.
    splashback_length_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    upstands: Mapped[bool] = mapped_column(Boolean, default=False)
    upstands_length_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    postcode: Mapped[str | None] = mapped_column(String, nullable=True)

    price_per_slab: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_before_vat: Mapped[float | None] = mapped_column(Float, nullable=True)
    vat: Mapped[float | None] = mapped_column(Float, nullable=True)
    total: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Sprint 036 (Workstream E) — the universal quote envelope. ---
    #
    # These describe the *job*, not the stone, and apply equally to a
    # roofing quote, a bathroom refit and a worktop run. All nullable so
    # no existing quote needs a backfill.
    #
    # `trade` is one of app/quotes/trades.py's TRADES (general_building,
    # renovation, extension, kitchen, bathroom, roofing, flooring,
    # decorating, plumbing, electrical, carpentry, stone, other) — plain
    # String validated at the Pydantic boundary, same convention as
    # status. Stone is one trade among twelve now, not the platform.
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    trade: Mapped[str | None] = mapped_column(String, nullable=True)

    site_address_line1: Mapped[str | None] = mapped_column(String, nullable=True)
    site_address_line2: Mapped[str | None] = mapped_column(String, nullable=True)
    site_city: Mapped[str | None] = mapped_column(String, nullable=True)
    site_postcode: Mapped[str | None] = mapped_column(String, nullable=True)

    scope_of_works: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    exclusions: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Money representation. `currency` is copied from the tenant at
    # creation rather than read live, so changing a workspace's currency
    # never silently re-denominates a document a customer already holds.
    # `vat_rate` replaces the calculator's hardcoded 0.20 for general
    # quotes; the stone calculator is untouched and still writes 20%.
    # `subtotal` is the pre-discount sum of line totals — `price_before_vat`
    # stays the post-discount taxable amount every existing reader
    # already understands, so no existing total changes meaning.
    currency: Mapped[str] = mapped_column(String, nullable=False, server_default="GBP")
    vat_rate: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.2")
    subtotal: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_amount: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Sprint 036 — "sent" joins "draft" and "approved". A quote a customer
    # has actually received is the thing worth chasing, and it is what the
    # quote.sent automation trigger and the "unanswered quote" follow-up
    # template key off. Approval accepts either draft or sent (see
    # QuoteService.approve) so nothing that could be approved before this
    # sprint stops being approvable.
    status: Mapped[str] = mapped_column(
        String, nullable=False, server_default="draft"
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["QuoteItem"]] = relationship(
        "QuoteItem", order_by="QuoteItem.position", cascade="all, delete-orphan", lazy="selectin"
    )


class QuoteItem(Base):
    """One structured line item on a Quote (Sprint 033, Workstream C —
    the true multi-line-item quote architecture deferred in Sprint 032
    §4). Every Quote has one or more of these; a quote created before
    this sprint gets exactly one backfilled row (migration
    `<see alembic revision>`) reconstructed from its own former scalar
    columns — never destroyed, never guessed.

    `item_type` is a plain string (same no-native-enum convention as
    Quote.status etc.), validated at the Pydantic boundary
    (app/quotes/models.py's ITEM_TYPES) — worktop/island/splashback/
    upstand/sill/waterfall_panel/other. Every type uses identical area
    math (quantity x length x width x wastage / slab area); island and
    waterfall_panel carry a small additional flat installation surcharge
    (see app/quotes/calculator.py) for continuity with Sprint 032's
    pricing, not because they need different dimension handling.
    """

    __tablename__ = "quote_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quote_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotes.id"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # Sprint 036 (Workstream E) — which pricing model this line uses.
    # "stone" keeps the slab maths below (material/thickness/dimensions ->
    # slabs -> line_total) exactly as Sprint 033 built it. "labour",
    # "material" and "other" are general construction lines priced as
    # quantity x unit_price, described in words rather than millimetres.
    # NOT NULL, server default "stone": every line that existed before
    # this sprint is a slab line.
    line_kind: Mapped[str] = mapped_column(String, nullable=False, server_default="stone")

    item_type: Mapped[str] = mapped_column(String, nullable=False, server_default="worktop")

    # Stone-only. Nullable since Sprint 036: a "Strip out existing
    # bathroom — 2 days labour" line has no material or thickness, and a
    # NOT NULL column would have forced a fake one.
    material: Mapped[str | None] = mapped_column(String, nullable=True)
    thickness: Mapped[str | None] = mapped_column(String, nullable=True)

    # Widened INTEGER -> DOUBLE PRECISION in Sprint 036. A stone line is
    # 2 slabs; a labour line is 2.5 days. Postgres widens in place with no
    # precision loss, and 1 and 1.0 are the same number to both Python's
    # == and JavaScript's ===, so no existing assertion or display
    # changes meaning.
    quantity: Mapped[float] = mapped_column(Float, nullable=False, server_default="1")
    length_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    width_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    thickness_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_input: Mapped[str] = mapped_column(String, nullable=False, server_default="mm")

    # General-line columns. `description` is what the customer reads on the
    # PDF; a stone line still derives its description from material and
    # dimensions (app/quotes/pdf.py's build_line_items), so this stays
    # NULL for stone. `unit` is free text from a curated list ("item",
    # "m", "m2", "hour", "day", "job", ...) — a label, never something
    # arithmetic is done with.
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)

    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    price_per_slab: Mapped[float | None] = mapped_column(Float, nullable=True)
    slabs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # This item's own contribution to the quote's price_before_vat
    # (material cost + any type-specific flat surcharge) — the Quote's
    # own price_before_vat is the sum of every item's line_total.
    line_total: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Sprint 012 — indexed: every query is now filtered by tenant_id (ADR-029).
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True
    )
    # Sprint 020 — traceable handoff source; nullable so historical projects
    # (created before handoff existed) remain valid. Unique: the DB-level
    # duplicate-handoff guard (one quote hands off to at most one project).
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotes.id"), nullable=True, unique=True
    )
    # Sprint 023 (docs/SPRINTS/sprint-023.md) — the responsible Staff/Owner
    # member, if any. No assigned_at column — ActivityLog's own timestamp
    # on each PROJECT_ASSIGNED event already gives an exact audit trail,
    # same no-updated_at-anywhere convention as every other table.
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String, nullable=False)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="enquiry")

    # --- Sprint 036 (Workstream F) — a real construction project record. ---
    #
    # All nullable, so every project created before this sprint stays
    # valid and the existing ProjectCreate/{name,customer_id,notes} body
    # keeps working unchanged.
    #
    # `project_type` is one of app/quotes/trades.py's TRADES — the same
    # vocabulary a quote uses, so an approved quote hands its trade
    # straight to the project it becomes rather than mapping between two
    # near-identical lists.
    #
    # `start_date`/`target_completion_date` are calendar Dates, not
    # timestamps: a job starts on a day, not at 09:00:00+01:00, and
    # storing a spurious time would make "starts tomorrow" automation
    # depend on an arbitrary hour.
    project_type: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    site_address_line1: Mapped[str | None] = mapped_column(String, nullable=True)
    site_address_line2: Mapped[str | None] = mapped_column(String, nullable=True)
    site_city: Mapped[str | None] = mapped_column(String, nullable=True)
    site_postcode: Mapped[str | None] = mapped_column(String, nullable=True)

    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # What this job is worth. Populated automatically from the originating
    # quote's total on handoff, and editable afterwards — a project's value
    # legitimately moves as variations are agreed, and the quote it came
    # from must never be retro-edited to match.
    estimated_value: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Task(Base):
    """A piece of internal work someone on the tenant needs to do (Sprint
    036). Deliberately one table serving four callers rather than four
    near-identical ones:

      * Workstream F — the extensible task foundation under a Project.
      * Workstream G — the `create_task` and `draft_message` automation
        actions.
      * Workstream C — "tasks requiring attention" on Dashboard V2.
      * Workstream K — dated items on the Calendar.

    `source_type`/`source_id` are the same deliberately-unconstrained
    polymorphic reference NotificationRecord already uses (Sprint 024):
    a task can hang off a project, a quote, a customer or nothing at all,
    which no single FK can express. Tenant/existence validation happens in
    the service, not the schema.

    `dedupe_key` carries the same idempotency invariant as
    NotificationRecord.dedupe_key — an automation that fires twice for the
    same subject creates one task, enforced by the UNIQUE constraint
    rather than only by a pre-check. Postgres treats multiple NULLs in a
    UNIQUE column as distinct, so manually-created tasks (which set no key)
    are unaffected.

    `body` exists for the `draft_message` action: a prepared message a
    human reviews and sends themselves. GeoCore has no outbound email, SMS
    or messaging infrastructure, so nothing in this system transmits it.
    """

    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "open" | "done" | "cancelled" — plain String, validated at the
    # Pydantic boundary (app/tasks/models.py's TaskStatus).
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="open")
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    source_type: Mapped[str | None] = mapped_column(String, nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Automation(Base):
    """One tenant-owned `trigger -> conditions -> actions` rule (Sprint
    036, Workstream G).

    `conditions` and `actions` are JSON columns — the first in this schema.
    The alternative (a normalised automation_conditions/automation_actions
    pair) was rejected: both are read whole, always as a complete rule,
    never queried into or joined against, and normalising them would add
    two tables and two round trips to express a list. Their shape is
    validated at the Pydantic boundary (app/automations/models.py) on
    every write, so nothing unvalidated reaches the column.

    `trigger_type` is a plain String from
    app/automations/triggers.py's TRIGGERS, same no-native-enum
    convention as everything else here.

    `template_key` records which seeded template this rule was created
    from (NULL for one built by hand). It is provenance, not behaviour —
    editing a rule never re-syncs it to its template.

    This is the one table in this schema that carries `updated_at`: unlike
    every domain row here, an automation is a piece of configuration a user
    edits repeatedly and expects to see a "last changed" time for, and its
    edits are not individually interesting enough to warrant an
    ActivityLog row each. Subscription (Sprint 032) set the same precedent
    for configuration-shaped rows.
    """

    __tablename__ = "automations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_key: Mapped[str | None] = mapped_column(String, nullable=True)

    trigger_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    actions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AutomationRun(Base):
    """One recorded attempt to execute an Automation (Sprint 036).

    Every attempt writes a row, including the ones that do nothing:
    "skipped" with a reason is the difference between an automation that is
    quietly broken and one that is correctly declining to fire. A failing
    automation must never break the user action that triggered it, so the
    dispatcher records `failed` with the exception text and swallows it —
    this table is the only place that failure is visible, which is why it
    is a first-class part of the feature rather than a log line.

    `dedupe_key` is `{automation_id}:{trigger}:{subject_id}` (plus a
    discriminator where one occurrence can legitimately recur). UNIQUE, so
    idempotency is enforced by the database and not merely attempted by a
    pre-check — the same defence-in-depth Sprint 024 established for
    notification dedupe.
    """

    __tablename__ = "automation_runs"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_automation_runs_dedupe_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    automation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automations.id"), nullable=False, index=True
    )

    trigger_type: Mapped[str] = mapped_column(String, nullable=False)
    subject_type: Mapped[str | None] = mapped_column(String, nullable=True)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # "succeeded" | "failed" | "skipped"
    status: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Material(Base):
    __tablename__ = "materials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True
    )

    name: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    thickness: Mapped[str | None] = mapped_column(String, nullable=True)
    slab_size: Mapped[str | None] = mapped_column(String, nullable=True)
    finish: Mapped[str | None] = mapped_column(String, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Sprint 009 — the first tenant_id column to actually become NOT NULL
    # (migration c28dd4348080); every user belongs to exactly one tenant.
    # The other 6 tables' tenant_id columns stay nullable until Sprint 012.
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )

    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # Sprint 010 — constrained to app.auth.models.UserRole's values at the
    # Pydantic/API boundary, same convention as Project.status/ProjectStatus.
    # Still a plain String column, no DB-level enum or CHECK constraint.
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Sprint 015 (docs/DECISIONS.md ADR-031) — soft-deactivation. An Owner
    # can revoke a teammate's access without deleting the row (Invitation.
    # invited_by_user_id / PortalLink.created_by_user_id are NOT NULL FKs to
    # this table, so deletion would break historical rows). See
    # app/users/service.py and app/auth/dependencies.py's get_current_user.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # Sprint 039 Production Readiness Defect Gate, Blocker 1 (migration
    # e1f2a3b4c5d6). NULL for every user until EmailVerificationService.
    # verify() sets it exactly once — see app/auth/dependencies.py's
    # require_verified_email() for how a NULL here is treated for users
    # created before this column existed (legacy grace period).
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Sprint 039 Production Readiness Defect Gate, Blocker 2 (migration
    # f2a3b4c5d6e7). NULL until a user resets their password for the
    # first time. get_current_user rejects any JWT whose `iat` claim
    # predates this timestamp, even if the token hasn't otherwise
    # expired — see app/auth/dependencies.py and app/auth/security.py's
    # create_access_token for how "reset revokes existing sessions" works
    # against stateless JWTs with no server-side session table.
    token_valid_after: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EmailVerificationToken(Base):
    """Proves the signup email's owner controls that inbox. Same opaque
    hashed-single-use-token shape as Invitation/PortalLink (token_hash,
    unique, never the recoverable secret) but a dedicated table rather
    than reusing either of those — this token authenticates a materially
    different claim ("you own this inbox") with its own lifecycle (many
    historical rows per user across resends, no status column needed:
    used_at nullable is enough since there is no "revoked" concept here).
    No relationship() (repo convention) — user_id is a plain FK column,
    resolved via explicit crud lookups.
    """

    __tablename__ = "email_verification_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PasswordResetToken(Base):
    """Same opaque hashed-single-use-token shape as Invitation/PortalLink
    (token_hash, unique, never the recoverable secret), but deliberately
    a dedicated table rather than reusing either — a stolen reset token
    grants immediate account takeover, a materially higher-stakes claim
    than either of those two tokens', with its own much shorter expiry
    (1h vs Invitation's 7 days / PortalLink's 90). No relationship()
    (repo convention) — user_id is a plain FK column, resolved via
    explicit crud lookups.
    """

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Invitation(Base):
    """A pending offer to join a tenant as a Staff user. Sprint 011 — the
    first table that lets a tenant have more than one user. No
    relationship() (repo convention) — tenant_id/invited_by_user_id are
    plain FK columns, resolved via explicit crud lookups.

    status is one of "pending" | "accepted" | "revoked" — plain String,
    same convention as User.role/Project.status. "expired" is derived at
    read time from expires_at, not stored. See docs/DECISIONS.md ADR-028.
    """

    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    invited_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    email: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="pending")

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PortalLink(Base):
    """A reusable, revocable link letting one customer view their own
    projects/quotes with no account (Sprint 013, ADR-030). Same opaque
    hashed-token convention as Invitation (token_hash, unique, never the
    recoverable secret) but NOT single-use: status is "active" | "revoked"
    only — there is no "accepted" state, since an active link is meant to
    be opened repeatedly until the Owner/Staff revokes it or it expires.
    "expired" is derived at read time from expires_at, same as
    Invitation's, never stored. No relationship() (repo convention) —
    tenant_id/customer_id/created_by_user_id are plain FK columns,
    resolved via explicit crud lookups.
    """

    __tablename__ = "portal_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="active")

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    """A file uploaded by staff against a customer, downloadable by staff
    and via that customer's portal link (Sprint 016, ADR-032). Customer-
    level, not project-level — same reasoning as PortalLink (ADR-030): one
    customer's document list serves all their concurrent jobs, no
    project-picker UI needed. storage_filename is a generated UUID-based
    name, never the user-supplied original_filename — original_filename is
    display/metadata only, never interpreted as a filesystem path (path
    traversal prevention by construction, see app/documents/service.py).
    No relationship() (repo convention) — every FK here is a plain column,
    resolved via explicit crud lookups.
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    uploaded_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    original_filename: Mapped[str] = mapped_column(String, nullable=False)
    storage_filename: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Message(Base):
    """One staff<->customer message on a customer's portal thread (Sprint
    017, ADR-033). Customer-level, not project-level — same reasoning as
    PortalLink/Document (ADR-030/ADR-032): one thread covers all of a
    customer's concurrent jobs. sender_user_id is populated for a
    staff-authored message and null for a customer-authored message,
    because portal customers have no users row. sender_type ("staff"|
    "customer") is the single source of truth for which side sent it —
    plain String, same convention as PortalLink.status/User.role. No
    relationship() (repo convention) — every FK here is a plain column,
    resolved via explicit crud lookups.
    """

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    sender_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    sender_type: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActivityLog(Base):
    """Table-ification of app/activity/models.py's ActivityEvent.

    Column names/types intentionally mirror the pydantic model so
    PostgresActivityRepository can map between them with no translation
    logic beyond str(uuid) <-> uuid.UUID.
    """

    __tablename__ = "activity_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Sprint 012 — indexed: every query is now filtered by tenant_id (ADR-029).
    # Stays nullable: seed rows and events logged from an anonymous /quote or
    # /estimate call have no tenant and are visible to no tenant's activity
    # feed — see ADR-029.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )

    type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class NotificationRecord(Base):
    """Table-ification of app/notifications/models.py's Notification.

    Named NotificationRecord, not Notification, to avoid colliding with the
    pydantic model app.notifications.models.Notification that the API
    already returns — PostgresNotificationRepository converts between them.
    """

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Sprint 012 — indexed: every query is now filtered by tenant_id (ADR-029).
    # Stays nullable: seed rows have no tenant and are visible to no tenant's
    # notification feed — see ADR-029.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False, default="info")
    read: Mapped[bool] = mapped_column(Boolean, default=False)

    # Sprint 024 (docs/SPRINTS/sprint-024.md) — all four nullable, existing
    # rows (tenant-wide broadcasts) stay valid untouched. NULL
    # recipient_user_id means "visible to the whole tenant", exactly
    # today's behavior; a set value scopes it to one user. source_id is
    # deliberately not an FK — it can point to different tables depending
    # on source_type (the first polymorphic reference in this schema), so
    # a single FK constraint can't express it; tenant/existence validation
    # happens in the service, not the schema.
    recipient_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    source_type: Mapped[str | None] = mapped_column(String, nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Idempotency invariant for automated notifications (unset for manual/
    # portal ones). Postgres treats multiple NULLs in a UNIQUE column as
    # distinct, so existing non-deduped rows are unaffected.
    dedupe_key: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Appointment(Base):
    """A staff-scheduled site visit against a Project (Sprint 022,
    docs/SPRINTS/sprint-022.md). No `customer_id` — the customer is reached
    via `project_id -> Project.customer_id`, avoiding duplication of a
    relationship the Project already provides. `tenant_id` is NOT NULL from
    creation (unlike Customer/Project/Quote's nullable columns, which exist
    for an anonymous-creation path this entity has no equivalent of). No
    `updated_at` — no table in this schema has one; a status transition is
    represented via ActivityLog, the same convention every other mutation
    in this codebase already follows."""

    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="scheduled")
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Subscription(Base):
    """A Tenant's GeoCore commercial subscription (Sprint 032, Workstream
    A). One row per tenant (unique tenant_id) — v1 billing is a single
    plan per business account, not per-user. `plan`/`billing_period`/
    `status` are plain strings (same no-native-enum convention as
    Project.status etc.) validated at the Pydantic/API boundary
    (app/billing/models.py). `stripe_subscription_id` is nullable because
    a tenant can exist with no subscription at all (pre-billing/legacy —
    see app/billing/entitlements.py for how that's treated) or with an
    Enterprise plan that has no Stripe object (contact-sales, not
    self-service checkout).
    """

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, unique=True, index=True
    )

    plan: Mapped[str] = mapped_column(String, nullable=False)
    billing_period: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="incomplete")

    stripe_customer_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String, nullable=True, unique=True, index=True
    )
    stripe_price_id: Mapped[str | None] = mapped_column(String, nullable=True)

    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProcessedStripeEvent(Base):
    """Idempotency ledger for Stripe webhooks (Sprint 032, Workstream A).
    Stripe explicitly recommends/expects retries — the same event id can
    arrive more than once. `id` is Stripe's own event id (e.g.
    "evt_..."), used as the primary key purely so a second delivery's
    INSERT fails on the existing-row constraint rather than needing a
    separate SELECT-then-INSERT race window.
    """

    __tablename__ = "processed_stripe_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Communication(Base):
    """One outbound email attempt (Sprint 038, docs/SPRINTS/sprint-038.md
    §5). Named `Communication`/`communications` rather than `Message` —
    that name and table are already taken by app/database/models.py's
    `Message` (Sprint 017, ADR-033: portal customer<->staff chat). This
    is a genuinely different thing: an auditable record of one attempted
    transmission out of the platform (invitation, quote, follow-up,
    project update, review request), not a conversation thread.

    Every row is written before the provider is ever called (status
    "queued") and updated in place as the attempt progresses — never
    replaced — so a crash mid-send still leaves an inspectable row rather
    than nothing. `status` values are only ever ones the provider can
    actually establish (see app/communications/models.py's
    `CommunicationStatus`): "delivered" is set only from a verified
    provider webhook event, never assumed from the send API accepting the
    request.

    No relationship() (repo convention) — every FK is a plain column,
    resolved via explicit crud lookups. No API key, token, or credential
    is ever stored on this table.

    Every subject FK below is `ondelete="SET NULL"` — this is an audit
    ledger, and a hard-deleted quote/invitation/etc. (which today only
    ever happens from a test's own cleanup SQL, since no product code path
    hard-deletes any of these) must not either block that delete via a
    dangling FK or silently take the communication history down with it.
    `tenant_id` deliberately has no such override: there is no code path,
    test or product, that hard-deletes a Tenant row.
    """

    __tablename__ = "communications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )

    # All nullable — which of these is set depends on message_type. A
    # quote-follow-up carries a quote_id; a team invitation carries none
    # of them.
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    quote_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    invitation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invitations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    automation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("automations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    automation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("automation_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    channel: Mapped[str] = mapped_column(String, nullable=False, server_default="email")
    direction: Mapped[str] = mapped_column(String, nullable=False, server_default="outbound")
    message_type: Mapped[str] = mapped_column(String, nullable=False)

    recipient: Mapped[str] = mapped_column(String, nullable=False)
    sender_identity: Mapped[str] = mapped_column(String, nullable=False)

    subject: Mapped[str] = mapped_column(String, nullable=False)
    # The content actually sent, snapshotted at send time — never
    # re-rendered from live data later, so a customer-history view stays
    # accurate even after a template or the underlying quote/project
    # changes. html/text are both stored so a plain-text fallback is
    # always available without re-rendering.
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)

    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="draft", index=True)

    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # "transient" | "permanent" | "suppressed" | None — drives whether the
    # delivery worker (Phase 3) retries or gives up. Never a raw provider
    # stack trace; failure_detail is deliberately short, user-facing text.
    failure_category: Mapped[str | None] = mapped_column(String, nullable=True)
    failure_detail: Mapped[str | None] = mapped_column(String, nullable=True)

    # Tenant-scoped idempotency key. A duplicate insert attempt (a retried
    # worker tick, a double-click) must resolve to the existing row, not a
    # second send — enforced by the unique index, same shape as
    # Notification.dedupe_key / Task.dedupe_key.
    dedupe_key: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "dedupe_key", name="uq_communications_tenant_dedupe_key"),
    )


class EmailSuppression(Base):
    """One email address this tenant must not be sent to again (Sprint
    038) — a hard bounce, a provider complaint, or a manual suppression.
    Checked by DeliveryService before every send attempt; automation
    execution respects it the same way.

    Tenant-scoped rather than global: one tenant's customer bouncing does
    not affect another tenant's ability to email that same address (a
    shared inbox at a supplier used by two different tenants' customers,
    for instance) — each tenant's sending reputation and suppression
    state is its own, matching every other per-tenant isolation boundary
    in this schema.
    """

    __tablename__ = "email_suppressions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String, nullable=False)
    # "hard_bounce" | "complaint" | "manual"
    reason: Mapped[str] = mapped_column(String, nullable=False)
    # The communication that caused this suppression, where applicable
    # (null for a manually-added suppression).
    source_communication_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("communications.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_email_suppressions_tenant_email"),
    )


class ProcessedEmailEvent(Base):
    """Idempotency ledger for the Resend webhook (Sprint 038, Phase 2).
    Same shape and reasoning as `ProcessedStripeEvent`: `id` is the
    webhook delivery's own unique id (the `svix-id` header — Resend's
    webhooks are delivered via Svix, which guarantees at-least-once
    delivery), used as the primary key so a second delivery's INSERT
    fails on the existing-row constraint rather than needing a separate
    SELECT-then-INSERT race window."""

    __tablename__ = "processed_email_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

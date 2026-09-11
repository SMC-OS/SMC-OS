"""Sprint 031 — safe removal of the Sprint 030 SIMO-LAUNCH-QA-* launch
fixture from production (docs/SPRINTS/sprint-031.md, Workstream C).

Design constraints (all enforced, not just documented):

- ORM/service-layer only. No raw SQL string is ever executed.
- Exact-identifier match only. The only inputs this script accepts are the
  literal names in QA_TENANT_NAMES/QA_MATERIAL_NAME/QA_MATERIAL_THICKNESS
  below — there is no wildcard, prefix-scan, or user-supplied selector of
  any kind, so there is nothing an operator could pass that broadens scope.
- Dry-run by default. Nothing is written unless --confirm is passed.
- Environment guard. Refuses to run against a database whose resolved host
  doesn't match the --environment the operator claims, without ever
  printing the resolved DATABASE_URL or any credential.
- One transaction. Every delete for a run happens inside a single
  Session/transaction; any unexpected error rolls back the entire run
  rather than leaving a partially-cleaned fixture.
- Prints counts only, never row contents.
- Idempotent. A second run against an already-cleaned database resolves
  zero tenants/materials and deletes nothing (dry-run and --confirm both
  report an empty plan cleanly, not an error).

Deletion order (leaf -> root), from the FK graph documented in
docs/SPRINTS/sprint-031.md §4 — no table here declares ON DELETE CASCADE,
so an out-of-order delete fails loudly with an IntegrityError rather than
silently cascading into unrelated data:

  Appointment, Document, Message, PortalLink, NotificationRecord,
  ActivityLog, Invitation, Project, QuoteItem, Quote, Customer, User, Tenant
  (Material is independent of all of the above — quotes.material/
  quotes.thickness are plain String columns, not a FK, per Sprint 030.
  QuoteItem (Sprint 033) has no tenant_id column of its own — it's
  deleted via a quote_id subquery, not the same tenant_id.in_(...) bulk
  pattern the other tenant-scoped tables use.)
"""

from __future__ import annotations

import argparse
import sys
import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.database import SessionLocal
from app.database.models import (
    ActivityLog,
    Appointment,
    Communication,
    Customer,
    Document,
    EmailSuppression,
    EmailVerificationToken,
    Invitation,
    Material,
    Message,
    NotificationRecord,
    PortalLink,
    Project,
    Quote,
    QuoteItem,
    Tenant,
    User,
)

QA_TENANT_NAMES: tuple[str, ...] = (
    "SIMO-LAUNCH-QA-TENANT-A",
    "SIMO-LAUNCH-QA-TENANT-B",
)
QA_MATERIAL_NAME = "SIMO-LAUNCH-QA-MATERIAL-001"
QA_MATERIAL_THICKNESS = "20mm"

# host substrings expected for each --environment value; verify_environment
# refuses to run unless the resolved DATABASE_URL host contains one of these.
_ENVIRONMENT_HOST_MARKERS: dict[str, tuple[str, ...]] = {
    "production": ("simo-postgres-production",),
    "staging": ("simo-postgres-staging", "postgres.railway.internal"),
}

# Tables deleted by tenant_id, in FK-safe leaf-to-root order. Every model
# here has a plain `tenant_id` column (confirmed against
# app/database/models.py) — no join through customer_id/project_id is
# needed even for Document/Message, which are tenant-scoped directly.
#
# Communication/EmailSuppression (Sprint 038) were never added here when
# that sprint shipped — a real gap, not exercised until Sprint 039's own
# signup-sends-a-verification-email change (Blocker 1) started leaving a
# real Communication row behind for every QA-fixture signup in this
# file's own tests, which then failed to delete a QA tenant with a real
# FK violation. Both tables' non-tenant_id FKs (customer/quote/project/
# invitation/automation/automation_run for Communication,
# source_communication_id for EmailSuppression) are all ondelete="SET
# NULL" (see Communication's own docstring), so their position in this
# list relative to Invitation/Project/Quote below doesn't matter — only
# that both come before the Tenant delete.
_TENANT_SCOPED_TABLES_IN_ORDER: tuple[type, ...] = (
    Appointment,
    Document,
    Message,
    PortalLink,
    NotificationRecord,
    ActivityLog,
    EmailSuppression,
    Communication,
    Invitation,
    Project,
    Quote,
    Customer,
    User,
)


class EnvironmentMismatchError(Exception):
    """Raised when --environment doesn't match the resolved database host."""


@dataclass
class CleanupPlan:
    tenant_ids: list[uuid.UUID]
    tenant_names: list[str]
    material_ids: list[uuid.UUID]
    # Anonymous quotes (tenant_id IS NULL — the public POST /api/v1/quote
    # path, ADR-023) whose customer_id belongs to one of the resolved QA
    # tenants. Untenanted, so invisible to every tenant_id-scoped query
    # above, but a real FK reference into a QA customer that must be
    # cleared before that customer can be deleted. Discovered against the
    # real Sprint 030 production fixture, not a hypothetical.
    orphan_quote_ids: list[uuid.UUID] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.tenant_ids and not self.material_ids and not self.orphan_quote_ids


def verify_environment(expected: str, database_url: str | None = None) -> None:
    """Refuse to run unless the resolved database host matches `expected`.
    Never logs or raises with the resolved URL/host in the message."""
    if expected not in _ENVIRONMENT_HOST_MARKERS:
        raise EnvironmentMismatchError(f"unknown --environment {expected!r}")
    url = database_url if database_url is not None else settings.database_url
    host = (make_url(url).host or "").lower()
    markers = _ENVIRONMENT_HOST_MARKERS[expected]
    if not any(marker in host for marker in markers):
        raise EnvironmentMismatchError(
            f"--environment {expected} does not match the resolved database host"
        )


def resolve_plan(db: Session) -> CleanupPlan:
    """Read-only. Exact-name match against QA_TENANT_NAMES/QA_MATERIAL_NAME
    only — never touches, counts, or reasons about any other row."""
    tenants = db.scalars(select(Tenant).where(Tenant.name.in_(QA_TENANT_NAMES))).all()
    tenant_ids = [tenant.id for tenant in tenants]
    tenant_names = [tenant.name for tenant in tenants]

    materials = db.scalars(
        select(Material).where(
            Material.name == QA_MATERIAL_NAME,
            Material.thickness == QA_MATERIAL_THICKNESS,
        )
    ).all()
    material_ids = [material.id for material in materials]

    counts: dict[str, int] = {"tenants": len(tenant_ids), "materials": len(material_ids)}
    orphan_quote_ids: list[uuid.UUID] = []
    quote_item_count = 0
    if tenant_ids:
        for model in _TENANT_SCOPED_TABLES_IN_ORDER:
            table_name = model.__tablename__
            counts[table_name] = (
                db.scalar(
                    select(func.count()).select_from(model).where(model.tenant_id.in_(tenant_ids))
                )
                or 0
            )

        # QuoteItem (Sprint 033) has no tenant_id column — counted via a
        # quote_id subquery instead of the bulk tenant_id.in_(...) pattern
        # every other table above uses.
        quote_item_count += (
            db.scalar(
                select(func.count())
                .select_from(QuoteItem)
                .where(QuoteItem.quote_id.in_(select(Quote.id).where(Quote.tenant_id.in_(tenant_ids))))
            )
            or 0
        )

        # EmailVerificationToken (Sprint 039 Production Readiness Defect
        # Gate, Blocker 1) has a user_id FK, not tenant_id — same
        # "counted via a subquery" treatment as QuoteItem above.
        counts["email_verification_tokens"] = (
            db.scalar(
                select(func.count())
                .select_from(EmailVerificationToken)
                .where(
                    EmailVerificationToken.user_id.in_(
                        select(User.id).where(User.tenant_id.in_(tenant_ids))
                    )
                )
            )
            or 0
        )

        customer_ids = db.scalars(
            select(Customer.id).where(Customer.tenant_id.in_(tenant_ids))
        ).all()
        if customer_ids:
            orphan_quote_ids = list(
                db.scalars(
                    select(Quote.id).where(
                        Quote.tenant_id.is_(None), Quote.customer_id.in_(customer_ids)
                    )
                ).all()
            )
    if orphan_quote_ids:
        quote_item_count += (
            db.scalar(
                select(func.count()).select_from(QuoteItem).where(QuoteItem.quote_id.in_(orphan_quote_ids))
            )
            or 0
        )
    counts["orphan_quotes"] = len(orphan_quote_ids)
    counts["quote_items"] = quote_item_count

    return CleanupPlan(
        tenant_ids=tenant_ids,
        tenant_names=tenant_names,
        material_ids=material_ids,
        orphan_quote_ids=orphan_quote_ids,
        counts=counts,
    )


def execute_plan(db: Session, plan: CleanupPlan) -> None:
    """Mutating. Deletes in FK-safe order inside the caller's transaction —
    this function never commits or rolls back; the caller controls that,
    so a failure here always leaves the decision to the caller rather than
    silently partially-committing."""
    if plan.is_empty:
        return
    if plan.orphan_quote_ids:
        # QuoteItem (Sprint 033) must precede its parent Quote; Quote
        # must precede the Customer delete below — an orphan quote's
        # customer_id FK would otherwise block it. No other ordering
        # constraint applies (an untenanted quote has no other dependents).
        db.execute(delete(QuoteItem).where(QuoteItem.quote_id.in_(plan.orphan_quote_ids)))
        db.execute(delete(Quote).where(Quote.id.in_(plan.orphan_quote_ids)))
    if plan.tenant_ids:
        # QuoteItem again precedes Quote, which is later in this same
        # loop — deleted first via its own quote_id subquery since it has
        # no tenant_id column to join the bulk pattern below.
        db.execute(
            delete(QuoteItem).where(
                QuoteItem.quote_id.in_(select(Quote.id).where(Quote.tenant_id.in_(plan.tenant_ids)))
            )
        )
        # EmailVerificationToken (Sprint 039 Production Readiness Defect
        # Gate, Blocker 1) again precedes User in this same loop below —
        # deleted first via its own user_id subquery, same treatment as
        # QuoteItem above.
        db.execute(
            delete(EmailVerificationToken).where(
                EmailVerificationToken.user_id.in_(
                    select(User.id).where(User.tenant_id.in_(plan.tenant_ids))
                )
            )
        )
        for model in _TENANT_SCOPED_TABLES_IN_ORDER:
            db.execute(delete(model).where(model.tenant_id.in_(plan.tenant_ids)))
        db.execute(delete(Tenant).where(Tenant.id.in_(plan.tenant_ids)))
    if plan.material_ids:
        db.execute(delete(Material).where(Material.id.in_(plan.material_ids)))


def _print_plan(plan: CleanupPlan, *, confirmed: bool) -> None:
    mode = "CONFIRMED CLEANUP" if confirmed else "DRY RUN"
    print(f"[{mode}] QA tenants matched: {len(plan.tenant_ids)} ({', '.join(plan.tenant_names) or 'none'})")
    for name, count in plan.counts.items():
        print(f"[{mode}]   {name}: {count}")
    if plan.is_empty:
        print(f"[{mode}] nothing to clean — already clean or fixture never existed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Remove the exact Sprint 030 SIMO-LAUNCH-QA-* launch fixture. Dry-run by default."
    )
    parser.add_argument(
        "--environment",
        required=True,
        choices=sorted(_ENVIRONMENT_HOST_MARKERS),
        help="Must match the resolved DATABASE_URL host or the script refuses to run.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually delete. Without this flag, the script only prints the plan.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        verify_environment(args.environment)
    except EnvironmentMismatchError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        plan = resolve_plan(db)
        _print_plan(plan, confirmed=args.confirm)
        if not args.confirm or plan.is_empty:
            db.rollback()
            return 0
        try:
            execute_plan(db, plan)
            db.commit()
        except Exception as exc:  # noqa: BLE001 — top-level job boundary, must never partially commit
            db.rollback()
            print(f"FAILED, rolled back entirely: {exc}", file=sys.stderr)
            return 1
    print("[CONFIRMED CLEANUP] committed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

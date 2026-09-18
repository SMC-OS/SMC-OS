"""Scan-evaluated automation triggers (Sprint 036, Workstream G).

Some useful automations describe a *state over time* rather than an event:
"this quote expires in three days and still hasn't been approved",
"this project starts tomorrow". No single database write corresponds to
those, so they cannot be dispatched from a service call. They are
evaluated by walking the relevant rows on a schedule.

Deliberately built in exactly the shape Sprint 024's FollowUpService
established, because that shape has already proven correct here:

  * takes an explicit `now` — so a test (or a staging verification run)
    can evaluate "three days before expiry" without waiting three days;
  * does no I/O beyond the session it is handed;
  * scans across every tenant, because a scheduled job has no caller and
    therefore no tenant — and tags every side effect with the subject
    row's own tenant_id, never a caller's;
  * is idempotent: the run dedupe key includes the day being evaluated,
    so running the job four times on Tuesday produces one task, and
    running it again on Wednesday correctly produces a new one only for a
    subject that is newly due.

Run via `python -m app.jobs.automations`, alongside the existing
`python -m app.jobs.follow_up`.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.automations.engine import automation_engine
from app.automations.subjects import project_subject, purchase_order_subject, quote_subject
from app.database import crud
from app.procurement.models import is_po_late

# How far ahead each scan trigger looks. Plain constants, not
# configuration: they are the smallest coherent choice, and making them
# per-tenant settings before anyone has asked would be configuration for
# its own sake. Both are trivially adjustable without a schema change.
QUOTE_EXPIRY_LOOKAHEAD = timedelta(days=3)
PROJECT_START_LOOKAHEAD = timedelta(days=1)

# Statuses a quote can be in and still be worth chasing. An approved quote
# is won and a draft was never sent, so neither is "unanswered".
_CHASEABLE_QUOTE_STATUSES = frozenset({"sent"})


@dataclass
class ScanResult:
    quotes_examined: int = 0
    projects_examined: int = 0
    purchase_orders_examined: int = 0
    runs_succeeded: int = 0
    runs_skipped: int = 0
    runs_failed: int = 0

    def as_dict(self) -> dict:
        return {
            "quotes_examined": self.quotes_examined,
            "projects_examined": self.projects_examined,
            "purchase_orders_examined": self.purchase_orders_examined,
            "runs_succeeded": self.runs_succeeded,
            "runs_skipped": self.runs_skipped,
            "runs_failed": self.runs_failed,
        }


class AutomationScanner:
    def run(self, db: Session, now: datetime) -> ScanResult:
        result = ScanResult()
        today = now.date()

        self._scan_expiring_quotes(db, now=now, today=today, result=result)
        self._scan_starting_projects(db, now=now, today=today, result=result)
        self._scan_overdue_deliveries(db, now=now, today=today, result=result)
        return result

    def _accumulate(self, result: ScanResult, engine_result) -> None:
        result.runs_succeeded += engine_result.succeeded
        result.runs_skipped += engine_result.skipped
        result.runs_failed += engine_result.failed

    def _scan_expiring_quotes(
        self, db: Session, *, now: datetime, today: date, result: ScanResult
    ) -> None:
        automations = crud.list_enabled_automations_by_trigger_all_tenants(
            db, "quote.expiring"
        )
        if not automations:
            return

        # Grouped by tenant once, so each quote is only ever evaluated
        # against its own workspace's rules. This is the isolation
        # boundary for the whole scan: a rule can never see a subject from
        # another tenant because it is never handed one.
        by_tenant: dict = {}
        for automation in automations:
            by_tenant.setdefault(automation.tenant_id, []).append(automation)

        for quote in crud.list_quotes_by_status(db, "sent"):
            if quote.tenant_id not in by_tenant:
                continue
            if quote.valid_until is None:
                continue
            if quote.status not in _CHASEABLE_QUOTE_STATUSES:
                continue

            due_from = quote.valid_until - QUOTE_EXPIRY_LOOKAHEAD
            if not (due_from <= today <= quote.valid_until):
                continue

            result.quotes_examined += 1
            customer = (
                crud.get_customer_by_id(db, quote.customer_id, quote.tenant_id)
                if quote.customer_id
                else None
            )
            engine_result = automation_engine.run_for_subject(
                db,
                tenant_id=quote.tenant_id,
                trigger_type="quote.expiring",
                subject=quote_subject(
                    quote, customer_name=customer.name if customer else ""
                ),
                now=now,
                automations=by_tenant[quote.tenant_id],
                # Keyed to the expiry date rather than to today, so the
                # whole three-day window produces one follow-up rather
                # than one per day.
                discriminator=f"expires:{quote.valid_until.isoformat()}",
            )
            self._accumulate(result, engine_result)

    def _scan_starting_projects(
        self, db: Session, *, now: datetime, today: date, result: ScanResult
    ) -> None:
        automations = crud.list_enabled_automations_by_trigger_all_tenants(
            db, "project.starting"
        )
        if not automations:
            return

        by_tenant: dict = {}
        for automation in automations:
            by_tenant.setdefault(automation.tenant_id, []).append(automation)

        for project in crud.list_projects_with_start_date(db):
            if project.tenant_id not in by_tenant:
                continue
            if project.status == "complete":
                continue

            due_from = project.start_date - PROJECT_START_LOOKAHEAD
            if not (due_from <= today <= project.start_date):
                continue

            result.projects_examined += 1
            customer = (
                crud.get_customer_by_id(db, project.customer_id, project.tenant_id)
                if project.customer_id
                else None
            )
            engine_result = automation_engine.run_for_subject(
                db,
                tenant_id=project.tenant_id,
                trigger_type="project.starting",
                subject=project_subject(
                    project, customer_name=customer.name if customer else ""
                ),
                now=now,
                automations=by_tenant[project.tenant_id],
                discriminator=f"starts:{project.start_date.isoformat()}",
            )
            self._accumulate(result, engine_result)

    def _scan_overdue_deliveries(
        self, db: Session, *, now: datetime, today: date, result: ScanResult
    ) -> None:
        """GeoCore Premium OS Plan 05 (Sprint 044), Task 26/28 — a PO is
        late only by is_po_late's own deterministic rule (a real expected
        date that has passed, on a PO not yet received/cancelled); a
        missing expected date is never treated as overdue. Discriminator
        is keyed to the day, so a PO stuck overdue for a week fires once
        per day rather than once ever or on every scan run that day."""
        automations = crud.list_enabled_automations_by_trigger_all_tenants(db, "delivery.overdue")
        if not automations:
            return

        by_tenant: dict = {}
        for automation in automations:
            by_tenant.setdefault(automation.tenant_id, []).append(automation)

        for purchase_order in crud.list_purchase_orders_with_expected_delivery(db):
            if purchase_order.tenant_id not in by_tenant:
                continue
            if not is_po_late(purchase_order.status, purchase_order.expected_delivery_date, today):
                continue

            result.purchase_orders_examined += 1
            project = (
                crud.get_project_by_id(db, purchase_order.project_id, purchase_order.tenant_id)
                if purchase_order.project_id
                else None
            )
            engine_result = automation_engine.run_for_subject(
                db,
                tenant_id=purchase_order.tenant_id,
                trigger_type="delivery.overdue",
                subject=purchase_order_subject(purchase_order, project_name=project.name if project else None),
                now=now,
                automations=by_tenant[purchase_order.tenant_id],
                discriminator=f"overdue:{today.isoformat()}",
            )
            self._accumulate(result, engine_result)


automation_scanner = AutomationScanner()

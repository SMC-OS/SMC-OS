"""Event dispatch — the seam between the domain services and the
automation engine (Sprint 036, Workstream G).

Why this is a separate module from the engine: the services that call it
(quotes, projects, customers) must not import the engine, the action
handlers or the trigger vocabulary. They call one narrow function per
event, named after the event, and know nothing else about automations.
That keeps the automation feature removable and keeps a circular import
between quote_service and the action that creates a project from a quote
confined to one lazy import inside actions.py.

Every dispatch here is called AFTER the triggering change has committed,
and every one is total: it never raises, so a broken rule can never turn a
successful quote approval into a 500. Failures are recorded as failed
AutomationRun rows, which is where the user sees them.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.automations.engine import automation_engine
from app.automations.subjects import (
    customer_subject,
    project_subject,
    quote_subject,
)
from app.database import crud
from app.projects import pipeline as project_pipeline
from app.projects import pipeline_config

logger = logging.getLogger("simo_os")


class AutomationDispatcher:
    def _customer_name(self, db: Session, customer_id, tenant_id) -> str:
        if customer_id is None:
            return ""
        customer = crud.get_customer_by_id(db, customer_id, tenant_id)
        return customer.name if customer is not None else ""

    def _dispatch(self, db: Session, *, tenant_id, trigger_type: str, subject: dict) -> None:
        """The one place an automation failure is contained.

        `tenant_id` may be None for an anonymous quote (ADR-023) — such a
        quote belongs to no workspace, so there are no rules to run and
        nothing to record.
        """
        if tenant_id is None:
            return
        try:
            automation_engine.run_for_subject(
                db,
                tenant_id=tenant_id,
                trigger_type=trigger_type,
                subject=subject,
                now=datetime.now(timezone.utc),
            )
        except Exception:  # noqa: BLE001
            # The engine already contains per-automation failures. Reaching
            # here means the dispatch itself failed (a dead session, say),
            # which must still not fail the user's request — but it is a
            # genuine defect, so it is logged rather than silently
            # discarded.
            db.rollback()
            logger.exception(
                "Automation dispatch failed",
                extra={"event": "automation_dispatch_failed", "trigger": trigger_type},
            )

    # --- Customers -----------------------------------------------------

    def dispatch_customer_created(self, db: Session, customer) -> None:
        self._dispatch(
            db,
            tenant_id=customer.tenant_id,
            trigger_type="customer.created",
            subject=customer_subject(customer),
        )

    # --- Quotes --------------------------------------------------------

    def _quote_subject(self, db: Session, quote) -> dict:
        return quote_subject(
            quote,
            customer_name=self._customer_name(db, quote.customer_id, quote.tenant_id),
        )

    def dispatch_quote_created(self, db: Session, quote) -> None:
        self._dispatch(
            db,
            tenant_id=quote.tenant_id,
            trigger_type="quote.created",
            subject=self._quote_subject(db, quote),
        )

    def dispatch_quote_sent(self, db: Session, quote) -> None:
        self._dispatch(
            db,
            tenant_id=quote.tenant_id,
            trigger_type="quote.sent",
            subject=self._quote_subject(db, quote),
        )

    def dispatch_quote_approved(self, db: Session, quote) -> None:
        self._dispatch(
            db,
            tenant_id=quote.tenant_id,
            trigger_type="quote.approved",
            subject=self._quote_subject(db, quote),
        )

    # --- Projects ------------------------------------------------------

    def _project_subject(self, db: Session, project, previous_status=None) -> dict:
        return project_subject(
            project,
            customer_name=self._customer_name(db, project.customer_id, project.tenant_id),
            previous_status=previous_status,
            pipeline=pipeline_config.resolve(db, project.tenant_id),
        )

    def dispatch_project_created(self, db: Session, project) -> None:
        self._dispatch(
            db,
            tenant_id=project.tenant_id,
            trigger_type="project.created",
            subject=self._project_subject(db, project),
        )

    def dispatch_project_status_changed(
        self, db: Session, project, previous_status: str
    ) -> None:
        subject = self._project_subject(db, project, previous_status=previous_status)

        # A status change fires two triggers when the new status is
        # "complete": the general one and the specific one. Both are
        # dispatched rather than making authors write
        # `status_changed AND status == complete` — "when a project is
        # finished" is the single most obviously useful automation a
        # builder will reach for, and it deserves its own trigger.
        #
        # The discriminator keeps their dedupe keys distinct, so a rule on
        # each fires once, and a project that somehow re-enters a status
        # does not silently no-op.
        self._dispatch_with_discriminator(
            db,
            tenant_id=project.tenant_id,
            trigger_type="project.status_changed",
            subject=subject,
            discriminator=project.status,
        )

        # Sprint 039 — "finished" is a role, not the literal stage key
        # "complete". A tenant on the standard pipeline finishes at
        # `completed`; a stone tenant finishes at `complete`; both fire
        # this trigger, and neither fires it at `cancelled`.
        if subject.get("status_role") == project_pipeline.COMPLETED:
            self._dispatch(
                db,
                tenant_id=project.tenant_id,
                trigger_type="project.completed",
                subject=subject,
            )

    def _dispatch_with_discriminator(
        self, db: Session, *, tenant_id, trigger_type: str, subject: dict, discriminator: str
    ) -> None:
        if tenant_id is None:
            return
        try:
            automation_engine.run_for_subject(
                db,
                tenant_id=tenant_id,
                trigger_type=trigger_type,
                subject=subject,
                now=datetime.now(timezone.utc),
                discriminator=discriminator,
            )
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception(
                "Automation dispatch failed",
                extra={"event": "automation_dispatch_failed", "trigger": trigger_type},
            )


automation_dispatcher = AutomationDispatcher()

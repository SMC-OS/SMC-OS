"""VariationService — GeoCore Premium OS Plan 04 (Sprint 043). Route-level
pattern (ADR-019): no repository interface, request-scoped Session via
get_db(), same shape as every other business module in this codebase.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.automations.dispatcher import automation_dispatcher
from app.database import crud
from app.database.models import Variation
from app.quotes.general import GeneralQuoteLineRequest, price as price_lines
from app.variations.models import (
    ALLOWED_TRANSITIONS,
    VariationCreate,
    VariationItemIn,
    VariationUpdate,
)


class ProjectNotFoundError(Exception):
    """Raised when the target Project doesn't resolve under the caller's
    own tenant — same tenant-scoped-lookup-hides-existence convention as
    every relationship check in this codebase (ADR-029)."""


class VariationNotFoundError(Exception):
    """Raised when the target Variation doesn't resolve under the
    caller's own tenant (not merely the wrong project) — same
    existence-hiding convention."""


class VariationEditStateError(Exception):
    """Raised when a variation's title/description/items are edited
    outside `draft` (Task 24 — an approved/sent/rejected/void variation
    is locked; a real correction is a new variation, never a rewrite)."""


class VariationTransitionError(Exception):
    """Raised when a status transition isn't legal from the variation's
    current status (see app.variations.models.ALLOWED_TRANSITIONS)."""


def _next_reference(db: Session, project_id: uuid.UUID, tenant_id: uuid.UUID) -> str:
    """Human-readable, per-project sequence — never the database id
    (Task 5). `count + 1` rather than tracking a separate counter row;
    UniqueConstraint("project_id", "reference") on the table is the
    backstop against the rare concurrent-create race, which is
    acceptable at V1's scale — see docs/SPRINTS/sprint-043.md."""
    count = crud.count_variations_for_project(db, project_id, tenant_id)
    return f"V-{count + 1:03d}"


def _price_items(items: list[VariationItemIn], vat_rate: float):
    # app/quotes/general.py's price() only ever reads `.quantity`/
    # `.unit_price` off each line — GeneralQuoteLineRequest is reused
    # directly rather than duplicating its rounding/VAT arithmetic in a
    # second commercial maths engine (Task 6/7).
    lines = [
        GeneralQuoteLineRequest(description=item.description, quantity=item.quantity, unit=item.unit, unit_price=item.unit_price)
        for item in items
    ]
    return price_lines(lines, vat_rate=vat_rate, discount_amount=None)


class VariationService:
    def _get_project(self, db: Session, project_id: uuid.UUID, tenant_id: uuid.UUID):
        project = crud.get_project_by_id(db, project_id, tenant_id)
        if project is None:
            raise ProjectNotFoundError(project_id)
        return project

    def _get_variation(self, db: Session, variation_id: uuid.UUID, tenant_id: uuid.UUID) -> Variation:
        variation = crud.get_variation_by_id(db, variation_id, tenant_id)
        if variation is None:
            raise VariationNotFoundError(variation_id)
        return variation

    def list_for_project(self, db: Session, project_id: uuid.UUID, tenant_id: uuid.UUID) -> list[Variation]:
        self._get_project(db, project_id, tenant_id)
        return crud.list_variations_by_project(db, project_id, tenant_id)

    def get(self, db: Session, variation_id: uuid.UUID, tenant_id: uuid.UUID) -> Variation:
        return self._get_variation(db, variation_id, tenant_id)

    def create(
        self,
        db: Session,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        data: VariationCreate,
    ) -> Variation:
        project = self._get_project(db, project_id, tenant_id)
        totals = _price_items(data.items, data.vat_rate)
        reference = _next_reference(db, project_id, tenant_id)

        variation = crud.create_variation(
            db,
            tenant_id=tenant_id,
            project_id=project_id,
            reference=reference,
            title=data.title,
            description=data.description,
            requested_by=data.requested_by,
            vat_rate=data.vat_rate,
            subtotal=totals.subtotal,
            vat=totals.vat,
            total=totals.total,
            created_by_user_id=actor_user_id,
        )
        crud.replace_variation_items(
            db,
            variation.id,
            [
                {
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "unit_price": item.unit_price,
                    "line_total": line_total,
                }
                for item, line_total in zip(data.items, totals.line_totals, strict=True)
            ],
        )
        db.refresh(variation)

        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.VARIATION_CREATED,
                title="Variation created",
                description=f"{project.name} — {variation.reference}: {variation.title} (£{variation.total:,.2f})",
            ),
            tenant_id=tenant_id,
        )
        automation_dispatcher.dispatch_variation_created(db, variation, project)
        return variation

    def update(
        self, db: Session, variation_id: uuid.UUID, tenant_id: uuid.UUID, data: VariationUpdate
    ) -> Variation:
        variation = self._get_variation(db, variation_id, tenant_id)
        if variation.status != "draft":
            raise VariationEditStateError(variation.status)

        changes = data.model_dump(exclude_unset=True, exclude={"items"})
        new_items = data.items if "items" in data.model_fields_set else None

        vat_rate = changes.get("vat_rate", variation.vat_rate)
        if new_items is not None:
            totals = _price_items(new_items, vat_rate)
            changes.update({"subtotal": totals.subtotal, "vat": totals.vat, "total": totals.total})

        variation = crud.update_variation(db, variation, changes)

        if new_items is not None:
            crud.replace_variation_items(
                db,
                variation.id,
                [
                    {
                        "description": item.description,
                        "quantity": item.quantity,
                        "unit": item.unit,
                        "unit_price": item.unit_price,
                        "line_total": line_total,
                    }
                    for item, line_total in zip(new_items, totals.line_totals, strict=True)
                ],
            )
            db.refresh(variation)
        return variation

    def _transition(
        self,
        db: Session,
        variation_id: uuid.UUID,
        tenant_id: uuid.UUID,
        *,
        target: str,
        actor_user_id: uuid.UUID | None = None,
    ) -> Variation:
        variation = self._get_variation(db, variation_id, tenant_id)

        # Idempotent: a retry of the exact same transition the variation
        # already completed is a no-op, never an error and never a
        # second side effect (Task 8's central regression — approving
        # the same variation twice must never double-count it; since
        # current_contract_value is *derived* by summing approved rows,
        # not incremented, a genuine re-approval couldn't double it
        # either, but this early return also keeps ActivityLog/
        # automations from firing twice for one real business event).
        if variation.status == target:
            return variation

        if target not in ALLOWED_TRANSITIONS.get(variation.status, set()):
            raise VariationTransitionError(f"{variation.status} -> {target}")

        changes: dict = {"status": target}
        if target == "approved":
            changes["approved_at"] = datetime.now(timezone.utc)
            changes["approved_by_user_id"] = actor_user_id

        variation = crud.update_variation(db, variation, changes)
        return variation

    def send(self, db: Session, variation_id: uuid.UUID, tenant_id: uuid.UUID) -> Variation:
        variation = self._transition(db, variation_id, tenant_id, target="sent")
        project = crud.get_project_by_id(db, variation.project_id, tenant_id)
        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.VARIATION_SENT,
                title="Variation sent",
                description=f"{project.name} — {variation.reference}: {variation.title}",
            ),
            tenant_id=tenant_id,
        )
        automation_dispatcher.dispatch_variation_sent(db, variation, project)
        return variation

    def approve(
        self, db: Session, variation_id: uuid.UUID, tenant_id: uuid.UUID, actor_user_id: uuid.UUID
    ) -> Variation:
        already_approved = self._get_variation(db, variation_id, tenant_id).status == "approved"
        variation = self._transition(
            db, variation_id, tenant_id, target="approved", actor_user_id=actor_user_id
        )
        if already_approved:
            return variation

        project = crud.get_project_by_id(db, variation.project_id, tenant_id)
        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.VARIATION_APPROVED,
                title="Variation approved",
                description=f"{project.name} — {variation.reference}: {variation.title} (£{variation.total:,.2f})",
            ),
            tenant_id=tenant_id,
        )
        automation_dispatcher.dispatch_variation_approved(db, variation, project)
        return variation

    def reject(self, db: Session, variation_id: uuid.UUID, tenant_id: uuid.UUID) -> Variation:
        variation = self._transition(db, variation_id, tenant_id, target="rejected")
        project = crud.get_project_by_id(db, variation.project_id, tenant_id)
        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.VARIATION_REJECTED,
                title="Variation rejected",
                description=f"{project.name} — {variation.reference}: {variation.title}",
            ),
            tenant_id=tenant_id,
        )
        automation_dispatcher.dispatch_variation_rejected(db, variation, project)
        return variation

    def void(self, db: Session, variation_id: uuid.UUID, tenant_id: uuid.UUID) -> Variation:
        variation = self._transition(db, variation_id, tenant_id, target="void")
        project = crud.get_project_by_id(db, variation.project_id, tenant_id)
        activity_service.log(
            ActivityEventCreate(
                type=ActivityType.VARIATION_VOIDED,
                title="Variation voided",
                description=f"{project.name} — {variation.reference}: {variation.title}",
            ),
            tenant_id=tenant_id,
        )
        return variation


variation_service = VariationService()

"""The automation engine (Sprint 036, Workstream G).

A pure domain service in the shape Sprint 024's FollowUpService
established: it takes an explicit `now`, does no I/O beyond the session it
is handed, prints nothing, and is therefore exhaustively unit-testable
without a running application.

Three invariants this module exists to guarantee:

1. **An automation can never break the thing that triggered it.** Every
   run is wrapped: an exception becomes a `failed` AutomationRun row with
   the message on it, and is swallowed. Approving a quote must not depend
   on the health of a rule someone wrote last Tuesday.

2. **Every attempt is visible.** Skipped runs are recorded too, with a
   reason. A rule that silently does nothing is indistinguishable from a
   broken one, and "why didn't my automation fire?" is the question this
   feature will be asked most.

3. **Running twice does the work once.** Each run computes a dedupe_key
   and both the pre-check and a UNIQUE constraint enforce it — the same
   defence-in-depth as Sprint 024's notification dedupe. Actions carry
   their own derived keys so a partially-failed run cannot double-create
   on retry.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.automations import triggers
from app.automations.actions import ActionError, perform
from app.automations.conditions import evaluate
from app.database import crud

SUCCEEDED = "succeeded"
FAILED = "failed"
SKIPPED = "skipped"


@dataclass
class EngineResult:
    """What one dispatch did. Returned so callers (the scan job, tests)
    can assert on outcomes without re-querying."""

    evaluated: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    details: list[str] = field(default_factory=list)


class AutomationEngine:
    def dedupe_key(
        self,
        automation_id: uuid.UUID,
        trigger_type: str,
        subject_id: str | None,
        discriminator: str | None = None,
    ) -> str:
        parts = [str(automation_id), trigger_type, str(subject_id)]
        if discriminator:
            parts.append(discriminator)
        return ":".join(parts)

    def run_for_subject(
        self,
        db: Session,
        *,
        tenant_id: uuid.UUID,
        trigger_type: str,
        subject: dict,
        now: datetime,
        automations=None,
        discriminator: str | None = None,
    ) -> EngineResult:
        """Evaluate every enabled automation for this trigger against one
        subject.

        `automations` may be passed by the scan job, which has already
        loaded the rules once for a whole batch of subjects rather than
        re-querying per subject. When omitted the rules are loaded here,
        tenant-scoped and enabled-only in SQL.
        """
        result = EngineResult()
        subject_type = triggers.subject_type_for(trigger_type)

        if automations is None:
            automations = crud.list_enabled_automations_for_trigger(
                db, tenant_id, trigger_type
            )

        for automation in automations:
            result.evaluated += 1
            key = self.dedupe_key(
                automation.id, trigger_type, subject.get("id"), discriminator
            )

            if crud.get_automation_run_by_dedupe_key(db, key) is not None:
                result.skipped += 1
                continue

            if not evaluate(automation.conditions, subject):
                self._record(
                    db,
                    automation=automation,
                    trigger_type=trigger_type,
                    subject=subject,
                    subject_type=subject_type,
                    status=SKIPPED,
                    detail="conditions not met",
                    # A skip for unmet conditions is NOT deduped: the same
                    # quote can legitimately fail a condition today and
                    # meet it tomorrow, and writing a permanent key here
                    # would block the later, real run.
                    dedupe_key=None,
                )
                result.skipped += 1
                continue

            outcomes: list[str] = []
            try:
                for index, action in enumerate(automation.actions or []):
                    outcomes.append(
                        perform(
                            db,
                            action=action,
                            tenant_id=tenant_id,
                            subject=subject,
                            # Per-action key derived from the run's, so a
                            # retry after a mid-run failure re-runs only
                            # what did not already happen.
                            dedupe_key=f"{key}#{index}",
                            now=now,
                            context={"subject_type": subject_type},
                        )
                    )
            except ActionError as exc:
                db.rollback()
                self._record(
                    db,
                    automation=automation,
                    trigger_type=trigger_type,
                    subject=subject,
                    subject_type=subject_type,
                    status=FAILED,
                    detail=str(exc),
                    dedupe_key=None,
                )
                result.failed += 1
                result.details.append(str(exc))
                continue
            except Exception as exc:  # noqa: BLE001 — see invariant 1 above
                # A genuinely unexpected failure inside a user-authored
                # rule. Recorded with its type so it is diagnosable, and
                # swallowed so the triggering request still succeeds.
                db.rollback()
                self._record(
                    db,
                    automation=automation,
                    trigger_type=trigger_type,
                    subject=subject,
                    subject_type=subject_type,
                    status=FAILED,
                    detail=f"{type(exc).__name__}: {exc}"[:500],
                    dedupe_key=None,
                )
                result.failed += 1
                continue

            recorded = self._record(
                db,
                automation=automation,
                trigger_type=trigger_type,
                subject=subject,
                subject_type=subject_type,
                status=SUCCEEDED,
                detail="; ".join(outcomes) or "no actions configured",
                dedupe_key=key,
            )
            if recorded:
                result.succeeded += 1
                result.details.extend(outcomes)
            else:
                result.skipped += 1

        return result

    def _record(
        self,
        db: Session,
        *,
        automation,
        trigger_type: str,
        subject: dict,
        subject_type: str | None,
        status: str,
        detail: str | None,
        dedupe_key: str | None,
    ) -> bool:
        subject_id = subject.get("id")
        try:
            parsed_subject_id = uuid.UUID(subject_id) if subject_id else None
        except ValueError:
            parsed_subject_id = None

        try:
            crud.create_automation_run(
                db,
                id=uuid.uuid4(),
                tenant_id=automation.tenant_id,
                automation_id=automation.id,
                trigger_type=trigger_type,
                subject_type=subject_type,
                subject_id=parsed_subject_id,
                status=status,
                detail=(detail or "")[:1000] or None,
                dedupe_key=dedupe_key,
            )
        except IntegrityError:
            # Lost the race on the UNIQUE dedupe_key. The other dispatch
            # already did this work; roll back so the session stays usable.
            db.rollback()
            return False
        return True


automation_engine = AutomationEngine()

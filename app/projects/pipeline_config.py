"""Resolving and seeding a tenant's own project pipeline (Sprint 039).

The database half of app/projects/pipeline.py. That module owns the
vocabulary and the transition graph and is pure; this one owns the
`pipeline_stages` rows and the fallback rules around them.

Two rules matter here:

1. **Resolution never fails.** A tenant with no configured stages
   resolves to the trade-neutral `standard` template rather than to an
   empty pipeline. Seeding happens at tenant creation
   (app/tenants/service.py) and happened for every pre-existing tenant in
   Sprint 039's migration, so this fallback should never fire in practice
   — but a project screen that cannot render because a row is missing is
   a far worse failure than a tenant quietly running on the default.

2. **Seeding never switches an already-configured tenant.**
   `seed_for_tenant` is idempotent and declines to act on a tenant that
   already has stages. Moving a live business from one pipeline to
   another rewrites the stage of every job it owns, which is
   `apply_template`'s job — a deliberate, previewed, Owner-only action,
   never a side effect of something else calling the seeder again.
"""

import uuid

from sqlalchemy.orm import Session

from app.database import crud
from app.projects.pipeline import (
    DEFAULT_TEMPLATE_KEY,
    Pipeline,
    Stage,
    template,
)


def resolve(db: Session, tenant_id: uuid.UUID) -> Pipeline:
    """This tenant's pipeline, falling back to the default template."""
    rows = crud.list_pipeline_stages(db, tenant_id)
    if not rows:
        return Pipeline(template(DEFAULT_TEMPLATE_KEY))
    return Pipeline(
        Stage(key=row.key, label=row.label, role=row.role, position=row.position)
        for row in rows
    )


def seed_for_tenant(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    template_key: str = DEFAULT_TEMPLATE_KEY,
    commit: bool = True,
) -> Pipeline:
    """Give a tenant with no pipeline the named template's stages.

    A no-op for a tenant that already has stages — see rule 2 above. The
    `commit` flag follows the same caller-owned-transaction convention as
    crud's own writes, so tenant creation can fold this into its
    transaction.
    """
    if crud.list_pipeline_stages(db, tenant_id):
        return resolve(db, tenant_id)

    stages = template(template_key)
    crud.create_pipeline_stages(
        db,
        tenant_id=tenant_id,
        stages=[
            {
                "key": stage.key,
                "label": stage.label,
                "role": stage.role,
                "position": stage.position,
            }
            for stage in stages
        ],
        template_key=template_key,
        commit=commit,
    )
    return Pipeline(stages)


def plan_template_change(
    db: Session, tenant_id: uuid.UUID, template_key: str
) -> dict[str, str]:
    """What switching this tenant to `template_key` would do to its jobs.

    Returns `{current_stage_key: new_stage_key}`, computed by *role* —
    a job that is "work under way" stays "work under way" whatever each
    pipeline calls it. Pure: reads, decides, writes nothing, so the UI can
    show a user the exact consequence before they agree to it.

    A current stage whose role has no counterpart in the target template
    is mapped to that template's earliest active stage, never dropped: a
    job must always land somewhere real.
    """
    current = resolve(db, tenant_id)
    target = Pipeline(template(template_key))
    fallback = target.initial_stage()

    mapping: dict[str, str] = {}
    for stage in current.stages:
        match = target.stage_for_role(stage.role)
        mapping[stage.key] = (match or fallback).key
    return mapping


def apply_template(db: Session, tenant_id: uuid.UUID, template_key: str) -> Pipeline:
    """Switch a tenant to a different pipeline, moving its jobs with it.

    The one place in Sprint 039 that does rewrite `projects.status`, and
    only ever because a person explicitly asked for it, having been shown
    `plan_template_change`'s mapping first.

    The stage rewrite and the stage-row replacement are one transaction:
    a tenant must never be left with jobs sitting on stage keys its
    pipeline no longer contains.
    """
    mapping = plan_template_change(db, tenant_id, template_key)
    stages = template(template_key)

    try:
        for current_key, new_key in mapping.items():
            if current_key != new_key:
                crud.move_projects_to_stage(
                    db, tenant_id, from_key=current_key, to_key=new_key, commit=False
                )
        crud.delete_pipeline_stages(db, tenant_id, commit=False)
        crud.create_pipeline_stages(
            db,
            tenant_id=tenant_id,
            stages=[
                {
                    "key": stage.key,
                    "label": stage.label,
                    "role": stage.role,
                    "position": stage.position,
                }
                for stage in stages
            ],
            template_key=template_key,
            commit=False,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return Pipeline(stages)


def attach_role(project, pipeline):
    """Attach the stage's trade-neutral role for `ProjectOut` to read.

    A transient attribute on the instance rather than a mapped column: the
    role is derived from tenant configuration, so persisting it alongside
    `status` would create a second copy of the same fact that could later
    disagree with the first. Unmapped attributes are untouched by flush,
    commit-expiry and refresh, so this survives every path that returns
    the row.

    Lives here rather than in ProjectService because two packages return a
    `Project` to a `ProjectOut` response — app/projects and
    app/quotes/router.py's handoff — and a role that is only attached by
    one of them is a `status_role: null` in the other's response.
    """
    if project is not None:
        project.status_role = pipeline.role_of(project.status)
    return project

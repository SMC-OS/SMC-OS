"""The workspace context GeoCore AI is given (Sprint 036, Workstream H).

An assistant that cannot see the business it is assisting can only produce
generic advice. This module builds a small, tenant-scoped, read-only
summary — counts and a handful of headline records — so answers to "what
needs my attention?" are grounded in this workspace's real state.

Three rules this module enforces, and the reasons they matter more here
than anywhere else in the codebase:

1. **Tenant-scoped by construction.** Every query takes the caller's own
   tenant_id. Nothing about another workspace can enter a prompt, because
   nothing about another workspace is ever loaded.

2. **Summary, not dump.** Counts, totals and at most a few titles. No
   customer email addresses, no phone numbers, no addresses, no message
   bodies, no document contents. Personal contact details have no business
   leaving the database for a third-party model to answer "how many quotes
   are outstanding", and sending them anyway would be a privacy decision
   made by accident.

3. **Bounded.** Fixed limits on every list, so a workspace with ten
   thousand projects produces the same size of prompt as one with ten.
"""

import uuid

from sqlalchemy.orm import Session

from app.database import crud

_HEADLINE_LIMIT = 5


def build(db: Session, tenant_id: uuid.UUID) -> dict:
    quotes = crud.list_quotes(db, tenant_id, limit=50)
    projects = crud.list_projects(db, tenant_id, limit=50)
    tasks = crud.list_tasks(db, tenant_id, status="open", limit=_HEADLINE_LIMIT)

    by_status: dict[str, int] = {}
    for quote in quotes:
        by_status[quote.status] = by_status.get(quote.status, 0) + 1

    project_status: dict[str, int] = {}
    # GeoCore Premium OS Plan 01 (Sprint 040, Task 7) — the semantic-role
    # sibling of project_status above, same rationale as the dashboard's
    # PipelineRoleCounts: a stone project on "Fabrication" and an
    # electrical one on "First Fix" both count under `in_progress`, so a
    # question like "what's in progress right now" is answerable across
    # every trade in one number, not one per trade. `project.workflow` is
    # already-loaded ORM data (no extra query), and its `role`/`stage_label`
    # are stable machine/display strings, not PII.
    project_role: dict[str, int] = {}
    for project in projects:
        project_status[project.status] = project_status.get(project.status, 0) + 1
        workflow = project.workflow
        if workflow is not None:
            project_role[workflow["role"]] = project_role.get(workflow["role"], 0) + 1

    return {
        "customers": crud.count_customers(db, tenant_id),
        "open_tasks": crud.count_open_tasks(db, tenant_id),
        "quotes": {
            "total_recent": len(quotes),
            "by_status": by_status,
            # A quote total is a price offered or committed to, never
            # recognised revenue — the Sprint 025 distinction, restated
            # here in the key name so a model cannot read it as income.
            "quoted_value_recent": round(sum(q.total or 0 for q in quotes), 2),
        },
        "projects": {
            "total_recent": len(projects),
            "by_status": project_status,
            "by_role": project_role,
        },
        # Titles only. Deliberately no customer names, emails, phone
        # numbers or addresses — see rule 2 above. Each project headline
        # now also carries its own trade workflow and stage label (e.g.
        # "Fabrication" on the "Stone & Worktops" workflow) — still just
        # names and machine-defined labels, no new PII.
        "recent_quote_titles": [
            q.title for q in quotes[:_HEADLINE_LIMIT] if q.title
        ],
        "recent_project_names": [p.name for p in projects[:_HEADLINE_LIMIT]],
        # Additive alongside recent_project_names above (never replacing
        # it — an existing consumer of the bare-name list keeps working
        # unchanged): the same headline projects, each now also carrying
        # its own trade workflow name and current stage label.
        "recent_projects": [
            {
                "name": project.name,
                "workflow_name": project.workflow["template_name"] if project.workflow else None,
                "stage_label": project.workflow["stage_label"] if project.workflow else None,
            }
            for project in projects[:_HEADLINE_LIMIT]
        ],
        "open_task_titles": [t.title for t in tasks],
    }

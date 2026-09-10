"""The trade-neutral project pipeline (Sprint 039, Workstream D).

**The idea in one line:** what a stage is *called* is tenant configuration;
what a stage *means* is a fixed, trade-neutral role, and every other module
in GeoCore reasons about the role.

That split is what makes this sprint's migration free of data risk. Sprint
006's pipeline — `enquiry → quoted → booked → templated → fabricated →
installed → complete` — is stone-industry vocabulary ("templating" is
measuring a worktop; "fabrication" is cutting the stone). Renaming it in
place would mean rewriting the `status` of every project ever created. It
does not need to be renamed in place: it survives verbatim as the `stone`
template, each of its stages annotated with the neutral role it always
meant, and the dashboard/automations/AI/calendar become trade-neutral
because they count roles rather than stage keys.

New tenants get the `standard` template, whose stage keys *are* the role
names — so from Sprint 039 onward, stone vocabulary is a specialism a
business opts into, never GeoCore's default identity.

**Transitions** (§4 Decision 5). Sprint 023's strict linear walk could not
express "this job is on hold" or "the customer cancelled", which every
construction business has. The graph here keeps Sprint 023's real
invariant — ordinary forward progress is still exactly one stage, never a
skip — and adds two side states:

  * `on_hold` is reachable from any active stage, and resumes to any active
    stage still in play. GeoCore has no basis for guessing where a held job
    should restart, and constraining it would add no safety. It can never
    resume straight into a terminal stage, so hold/resume is not a back
    door to marking a job finished.
  * `cancelled` is reachable from any non-terminal stage, and is terminal.

This module is pure: no database, no session, no I/O. Resolving which
template a given tenant is on lives in app/projects/pipeline_config.py.
"""

from dataclasses import dataclass

# --- The vocabulary every other module reasons about ---------------------

LEAD = "lead"
QUOTED = "quoted"
APPROVED = "approved"
SCHEDULED = "scheduled"
IN_PROGRESS = "in_progress"
COMPLETED = "completed"
ON_HOLD = "on_hold"
CANCELLED = "cancelled"

#: Ordinary forward progress, in order. A pipeline's own stages are ordered
#: by their `position`, not by this tuple — a template may have several
#: stages sharing one role (stone has three `in_progress` stages) or skip a
#: role entirely (the stone pipeline has no `scheduled` stage).
ACTIVE_ROLE_ORDER: tuple[str, ...] = (
    LEAD,
    QUOTED,
    APPROVED,
    SCHEDULED,
    IN_PROGRESS,
    COMPLETED,
)

#: Not part of forward progress. Every pipeline carries both.
SIDE_ROLES: tuple[str, ...] = (ON_HOLD, CANCELLED)

#: Nothing transitions out of these.
TERMINAL_ROLES: tuple[str, ...] = (COMPLETED, CANCELLED)

ROLES: frozenset[str] = frozenset(ACTIVE_ROLE_ORDER) | frozenset(SIDE_ROLES)


@dataclass(frozen=True)
class Stage:
    """One stage of one tenant's pipeline.

    `key` is what is persisted in `projects.status` and must stay stable
    for a tenant once used. `label` is display text. `role` is the
    trade-neutral meaning every other module keys off. `position` is the
    stage's place in this tenant's own order; side states sort after every
    active stage.
    """

    key: str
    label: str
    role: str
    position: int

    @property
    def is_terminal(self) -> bool:
        return self.role in TERMINAL_ROLES

    @property
    def is_side_state(self) -> bool:
        return self.role in SIDE_ROLES


def _stages(*rows: tuple[str, str, str]) -> tuple[Stage, ...]:
    return tuple(
        Stage(key=key, label=label, role=role, position=index)
        for index, (key, label, role) in enumerate(rows)
    )


# The two side states, identical in every template. Appended rather than
# defined per-template so a future template cannot accidentally omit the
# ability to hold or cancel a job.
_SIDE_STATE_ROWS: tuple[tuple[str, str, str], ...] = (
    (ON_HOLD, "On hold", ON_HOLD),
    (CANCELLED, "Cancelled", CANCELLED),
)

_TEMPLATES: dict[str, tuple[Stage, ...]] = {
    # GeoCore's default. Deliberately keyed by role: a business that has
    # not chosen a specialism should never meet a stone term.
    "standard": _stages(
        (LEAD, "Planning", LEAD),
        (QUOTED, "Quoted", QUOTED),
        (APPROVED, "Approved", APPROVED),
        (SCHEDULED, "Scheduled", SCHEDULED),
        (IN_PROGRESS, "In progress", IN_PROGRESS),
        (COMPLETED, "Completed", COMPLETED),
        *_SIDE_STATE_ROWS,
    ),
    # Sprint 006's pipeline, unchanged, now labelled as the specialism it
    # always was. Every existing tenant is seeded with this, which is why
    # the Sprint 039 migration rewrites no project rows.
    "stone": _stages(
        ("enquiry", "Enquiry", LEAD),
        ("quoted", "Quoted", QUOTED),
        ("booked", "Booked", APPROVED),
        ("templated", "Templated", IN_PROGRESS),
        ("fabricated", "Fabricated", IN_PROGRESS),
        ("installed", "Installed", IN_PROGRESS),
        ("complete", "Complete", COMPLETED),
        *_SIDE_STATE_ROWS,
    ),
}

TEMPLATE_KEYS: tuple[str, ...] = tuple(_TEMPLATES)

#: What a tenant gets when nobody has chosen otherwise.
DEFAULT_TEMPLATE_KEY = "standard"

#: What existing tenants were seeded with by Sprint 039's migration.
LEGACY_TEMPLATE_KEY = "stone"


def template(name: str) -> tuple[Stage, ...]:
    """The stages of a named template.

    Raises `KeyError` for an unknown name rather than quietly handing back
    the default — a caller asking for a template that does not exist has a
    bug, and silently substituting a different pipeline would hide it.
    """
    return _TEMPLATES[name]


class Pipeline:
    """One tenant's resolved stage list, plus the transition graph over it.

    Constructed from whatever stages a tenant actually has (from
    configuration, or from a template), so it never assumes the standard
    vocabulary.
    """

    def __init__(self, stages) -> None:
        self._stages: tuple[Stage, ...] = tuple(
            sorted(stages, key=lambda stage: stage.position)
        )
        self._by_key: dict[str, Stage] = {stage.key: stage for stage in self._stages}

    @property
    def stages(self) -> tuple[Stage, ...]:
        return self._stages

    @property
    def active_stages(self) -> tuple[Stage, ...]:
        """Forward-progress stages only, in this tenant's own order."""
        return tuple(stage for stage in self._stages if not stage.is_side_state)

    def get(self, key: str) -> Stage | None:
        return self._by_key.get(key)

    def role_of(self, key: str) -> str | None:
        stage = self._by_key.get(key)
        return stage.role if stage is not None else None

    def initial_stage(self) -> Stage:
        """Where a newly created project starts."""
        return self.active_stages[0]

    def stage_for_role(self, role: str) -> Stage | None:
        """The earliest stage carrying `role`.

        The cross-module entry point: `app/quotes/service.py` hands a quote
        off to "whatever this tenant calls approved" without ever naming a
        stage key, and the stale-enquiry scan looks for `lead` rather than
        for `"enquiry"`.
        """
        return next((stage for stage in self._stages if stage.role == role), None)

    def allowed_transitions(self, from_key: str) -> tuple[str, ...]:
        """Every stage key a project currently on `from_key` may move to.

        An unknown `from_key` yields no transitions rather than raising: a
        project can legitimately be sitting on a stage its tenant has since
        reconfigured away, and that must refuse the transition, not 500 the
        status endpoint.
        """
        current = self._by_key.get(from_key)
        if current is None or current.is_terminal:
            return ()

        cancelled = self._by_key.get(CANCELLED)
        on_hold = self._by_key.get(ON_HOLD)

        if current.role == ON_HOLD:
            # Resume to anything still genuinely in play. Terminal stages
            # are excluded on purpose — finishing a job is always its own
            # forward step, never a side effect of coming off hold.
            targets = [
                stage.key for stage in self.active_stages if not stage.is_terminal
            ]
        else:
            targets = []
            active = self.active_stages
            index = active.index(current) if current in active else None
            if index is not None and index + 1 < len(active):
                targets.append(active[index + 1].key)
            if on_hold is not None:
                targets.append(on_hold.key)

        if cancelled is not None:
            targets.append(cancelled.key)
        return tuple(targets)

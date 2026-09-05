"""Condition evaluation for automations (Sprint 036, Workstream G).

A condition is `{field, op, value}` evaluated against a **flat, explicitly
constructed subject dict** — never against an ORM row.

That distinction is the security property of this module. If conditions
were evaluated with `getattr(row, field)`, a user-authored rule could name
any column, any relationship, or any Python attribute on the model
(including `metadata`, `registry`, or another tenant's rows reachable
through a relationship). Because the subject is built by
app/automations/subjects.py from an explicit list of keys, a condition can
only ever see what that module deliberately exposed, and an unknown field
is a definite `False` rather than an accidental disclosure.

The operator set is deliberately small. There is no arbitrary expression
language, no `eval`, no regular expressions (which are a denial-of-service
surface when user-authored), and no boolean tree: conditions are ANDed.
"OR" is expressible today as two automations, which is also easier for a
builder to read than a nested rule.
"""

from typing import Any

OPS = frozenset({"eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte", "contains"})


def _compare(op: str, actual: Any, expected: Any) -> bool:
    if op == "eq":
        return actual == expected
    if op == "ne":
        return actual != expected
    if op == "in":
        return isinstance(expected, (list, tuple)) and actual in expected
    if op == "not_in":
        return isinstance(expected, (list, tuple)) and actual not in expected
    if op == "contains":
        # Substring match on text, membership on a list. Case-insensitive
        # for text because a rule author writing "kitchen" means to match
        # "Kitchen refit" — a case-sensitive match here would be a
        # silently-never-firing automation, the worst failure mode this
        # feature has.
        if isinstance(actual, str) and isinstance(expected, str):
            return expected.lower() in actual.lower()
        if isinstance(actual, (list, tuple)):
            return expected in actual
        return False

    # Ordered comparisons. A None on either side is not "less than"
    # anything — an absent value must not accidentally satisfy
    # "value < 5000". Mixed types (str vs int) would raise in Python, so
    # they are rejected rather than allowed to crash a dispatch.
    if actual is None or expected is None:
        return False
    if isinstance(actual, bool) != isinstance(expected, bool):
        return False
    if not isinstance(actual, (int, float)) or not isinstance(expected, (int, float)):
        if not (isinstance(actual, str) and isinstance(expected, str)):
            return False

    if op == "gt":
        return actual > expected
    if op == "gte":
        return actual >= expected
    if op == "lt":
        return actual < expected
    if op == "lte":
        return actual <= expected
    return False


def evaluate(conditions: list[dict] | None, subject: dict) -> bool:
    """All conditions must hold. No conditions means "always" — an
    automation with an empty condition list is a valid, useful rule
    ("every time a quote is approved, ...")."""
    if not conditions:
        return True

    for condition in conditions:
        field = condition.get("field")
        op = condition.get("op")
        if op not in OPS or field not in subject:
            # An unknown field or operator makes the whole rule false, and
            # deliberately so: silently ignoring the condition would run
            # the actions of a rule the author believes is narrowly
            # scoped. Failing closed is the only safe direction here.
            return False
        if not _compare(op, subject[field], condition.get("value")):
            return False

    return True

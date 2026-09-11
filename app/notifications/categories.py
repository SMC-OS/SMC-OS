"""What GeoCore can notify someone about (Sprint 039, Workstream B).

The rule this module exists to enforce, inherited from Sprint 036's own
notification-settings docstring: **every category here controls something
GeoCore genuinely does.** A preference that switches off a notification
which never fires is a mock with a database table behind it, and is worse
than no setting at all — it teaches a user that the settings screen lies.

So the list is short, and each entry names a real notification path:

  quote_activity        automations whose subject is a quote
  project_activity      automations whose subject is a project, and the
                        stale-lead follow-up scan
  customer_activity     automations whose subject is a customer
  task_assignment       a task an automation created and assigned to you
  automation_outcome    an automation that failed to run
  communication_failure an email to a customer that bounced or failed

Two channels, and only two, for the same reason: in-app (the bell menu,
which has existed since Sprint 001) and email (real since Sprint 038).
There is no SMS or push toggle because there is no SMS or push.

**Defaults preserve today's behaviour exactly.** In-app is on for every
category, which is what the `localStorage` card defaulted to. Email is off
for every category, so upgrading to Sprint 039 never starts sending a
person mail they did not ask for — opting in is a deliberate act.
"""

from dataclasses import dataclass

IN_APP = "in_app"
EMAIL = "email"
CHANNELS: tuple[str, ...] = (IN_APP, EMAIL)


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    description: str
    #: In-app is on by default — exactly what every user has today.
    default_in_app: bool = True
    #: Email is off by default. Turning this on is always a person's own
    #: decision, never an upgrade's side effect.
    default_email: bool = False


CATEGORIES: tuple[Category, ...] = (
    Category(
        "quote_activity",
        "Quote activity",
        "When a quote is approved, or is about to expire.",
    ),
    Category(
        "project_activity",
        "Project activity",
        "When a job changes stage, is about to start, or has sat untouched.",
    ),
    Category(
        "customer_activity",
        "New customers",
        "When a customer is added to the workspace.",
    ),
    Category(
        "task_assignment",
        "Tasks assigned to you",
        "When an automation creates a piece of work and puts your name on it.",
    ),
    Category(
        "automation_outcome",
        "Automation problems",
        "When one of your automations fails to run. An automation that has "
        "quietly stopped working is the failure this exists to catch.",
    ),
    Category(
        "communication_failure",
        "Delivery failures",
        "When an email to one of your customers bounces or can't be sent.",
    ),
)

CATEGORY_KEYS: frozenset[str] = frozenset(category.key for category in CATEGORIES)

_BY_KEY = {category.key: category for category in CATEGORIES}

#: Which category an automation's notification belongs to, derived from the
#: trigger's subject type (app/automations/triggers.py). Kept as an explicit
#: map rather than a naming convention so adding a trigger subject cannot
#: silently invent a category nobody can switch off.
_BY_SUBJECT_TYPE = {
    "quote": "quote_activity",
    "project": "project_activity",
    "customer": "customer_activity",
}


def get(key: str) -> Category | None:
    return _BY_KEY.get(key)


def for_subject_type(subject_type: str | None) -> str | None:
    """The category for an automation subject, or None if there isn't one.

    None is meaningful: `preferences.notify()` treats an uncategorised
    notification as always allowed. Failing *open* is deliberate — a
    subject type this build has not been taught about must not silently
    swallow a user's notification.
    """
    return _BY_SUBJECT_TYPE.get(subject_type) if subject_type else None


def default_for(category_key: str, channel: str) -> bool:
    category = _BY_KEY.get(category_key)
    if category is None:
        # An unknown category has no stored default to consult. In-app
        # defaults to on for the same fail-open reason as above; email
        # stays off, because nothing should ever start mailing a person
        # from a code path this module does not recognise.
        return channel == IN_APP
    return category.default_in_app if channel == IN_APP else category.default_email

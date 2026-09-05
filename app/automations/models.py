"""Pydantic boundary for automations (Sprint 036, Workstream G).

`conditions` and `actions` are stored as JSONB, which means this module is
the only thing standing between a user-authored payload and a column with
no shape. Every condition and every action is validated here on every
write — trigger key, condition operator, action type, and the config keys
each action actually understands. Anything unrecognised is rejected at the
API boundary rather than discovered later inside a dispatch, where the
only visible symptom would be a failed run.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.automations.actions import ACTION_TYPES
from app.automations.conditions import OPS
from app.automations.templates import TEMPLATE_KEYS
from app.automations.triggers import TRIGGER_KEYS

MAX_CONDITIONS = 10
MAX_ACTIONS = 5


class AutomationCondition(BaseModel):
    field: str = Field(min_length=1, max_length=64)
    op: str
    # Deliberately untyped: a condition compares against a string, a
    # number, a bool or a list depending on the field. The comparison
    # itself is total (app/automations/conditions.py never raises on a
    # type mismatch, it returns False), so an unhelpful value produces a
    # rule that doesn't match rather than a crash.
    value: object = None

    @field_validator("op")
    @classmethod
    def _known_op(cls, value: str) -> str:
        if value not in OPS:
            raise ValueError(f"op must be one of {sorted(OPS)}")
        return value


class AutomationAction(BaseModel):
    type: str
    config: dict = Field(default_factory=dict)

    @field_validator("type")
    @classmethod
    def _known_action(cls, value: str) -> str:
        if value not in ACTION_TYPES:
            raise ValueError(f"type must be one of {sorted(ACTION_TYPES)}")
        return value

    @model_validator(mode="after")
    def _known_config_keys(self) -> "AutomationAction":
        allowed = {"title", "message", "body", "due_in_days"}
        unknown = set(self.config) - allowed
        if unknown:
            raise ValueError(
                f"unknown config key(s) for action {self.type}: {sorted(unknown)}"
            )
        for key in ("title", "message", "body"):
            value = self.config.get(key)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{key} must be text")
            # Bounded so one automation cannot write an unbounded string
            # into every task it creates.
            if isinstance(value, str) and len(value) > 2000:
                raise ValueError(f"{key} must be 2000 characters or fewer")
        return self


class AutomationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    trigger_type: str
    conditions: list[AutomationCondition] = Field(default_factory=list, max_length=MAX_CONDITIONS)
    actions: list[AutomationAction] = Field(min_length=1, max_length=MAX_ACTIONS)
    enabled: bool = True

    @field_validator("trigger_type")
    @classmethod
    def _known_trigger(cls, value: str) -> str:
        if value not in TRIGGER_KEYS:
            raise ValueError(f"trigger_type must be one of {sorted(TRIGGER_KEYS)}")
        return value


class AutomationFromTemplate(BaseModel):
    """Activate a seeded template. Only the key is accepted: the point of a
    template is that the user does not have to compose a rule, and letting
    the request override its actions would make "which template is this"
    meaningless. Edit it afterwards through PATCH like any other rule."""

    template_key: str
    enabled: bool = True

    @field_validator("template_key")
    @classmethod
    def _known_template(cls, value: str) -> str:
        if value not in TEMPLATE_KEYS:
            raise ValueError(f"template_key must be one of {sorted(TEMPLATE_KEYS)}")
        return value


class AutomationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    trigger_type: str | None = None
    conditions: list[AutomationCondition] | None = Field(default=None, max_length=MAX_CONDITIONS)
    actions: list[AutomationAction] | None = Field(default=None, max_length=MAX_ACTIONS)
    enabled: bool | None = None

    @field_validator("trigger_type")
    @classmethod
    def _known_trigger(cls, value: str | None) -> str | None:
        if value is not None and value not in TRIGGER_KEYS:
            raise ValueError(f"trigger_type must be one of {sorted(TRIGGER_KEYS)}")
        return value

    @field_validator("actions")
    @classmethod
    def _at_least_one_action(
        cls, value: list[AutomationAction] | None
    ) -> list[AutomationAction] | None:
        if value is not None and not value:
            raise ValueError("an automation must have at least one action")
        return value


class AutomationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    template_key: str | None
    trigger_type: str
    conditions: list
    actions: list
    enabled: bool
    created_at: datetime
    updated_at: datetime


class AutomationRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    automation_id: uuid.UUID
    trigger_type: str
    subject_type: str | None
    subject_id: uuid.UUID | None
    status: str
    detail: str | None
    created_at: datetime

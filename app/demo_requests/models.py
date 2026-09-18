"""Public "Request a Demo" request/response schemas (Sprint 041).

Every field here is what a public, unauthenticated visitor may submit.
`status` and `source` are deliberately absent from this model — the
service layer assigns them server-side (Task 18: never trust a
client-supplied status/source/admin field).
"""

import re

from pydantic import BaseModel, Field, field_validator

from app.trades.catalogue import TRADE_KEYS

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PHONE_RE = re.compile(r"^[0-9+()\-\s]{6,30}$")

TEAM_SIZE_OPTIONS = ("1", "2-3", "4-10", "11-25", "26-50", "50+")
CONTACT_METHOD_OPTIONS = ("email", "phone")


class DemoRequestCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    company_name: str = Field(min_length=1, max_length=200)
    team_size: str
    trades: list[str] = Field(min_length=1, max_length=10)
    current_system: str | None = Field(default=None, max_length=500)
    message: str | None = Field(default=None, max_length=2000)
    preferred_contact_method: str | None = None

    # Honeypot — a real visitor never fills this (it is hidden from the
    # rendered form via CSS, not simply absent from the markup). Accepted
    # here so the service layer can detect and silently discard a bot
    # submission rather than the field failing validation and tipping the
    # bot off that something is being checked.
    website: str | None = None

    @field_validator("email")
    @classmethod
    def email_must_look_like_an_email(cls, value: str) -> str:
        if not _EMAIL_RE.match(value.strip()):
            raise ValueError("Enter a valid email address.")
        return value.strip().lower()

    @field_validator("phone")
    @classmethod
    def phone_must_be_a_plausible_shape(cls, value: str | None) -> str | None:
        if value is None or value.strip() == "":
            return None
        stripped = value.strip()
        if not _PHONE_RE.match(stripped):
            raise ValueError("Enter a valid phone number.")
        return stripped

    @field_validator("team_size")
    @classmethod
    def team_size_must_be_a_known_option(cls, value: str) -> str:
        if value not in TEAM_SIZE_OPTIONS:
            raise ValueError(f"team_size must be one of {list(TEAM_SIZE_OPTIONS)}")
        return value

    @field_validator("trades")
    @classmethod
    def every_trade_must_be_in_the_canonical_catalogue(cls, value: list[str]) -> list[str]:
        unknown = [key for key in value if key not in TRADE_KEYS]
        if unknown:
            raise ValueError(f"Unknown trade key(s): {unknown}")
        return value

    @field_validator("preferred_contact_method")
    @classmethod
    def contact_method_must_be_a_known_option(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value not in CONTACT_METHOD_OPTIONS:
            raise ValueError(f"preferred_contact_method must be one of {list(CONTACT_METHOD_OPTIONS)}")
        return value


class DemoRequestSubmitOut(BaseModel):
    # Deliberately no `id` or any other internal identifier — a public,
    # unauthenticated caller never needs one and it is not leaked.
    message: str = "Demo request received. We'll contact you using the details you provided."

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.trades.catalogue import TRADE_KEYS

# Sprint 036 — the currencies GeoCore can actually render correctly
# (a symbol on a PDF, a browser Intl format in the UI). Deliberately
# short: adding a code GeoCore cannot print would produce documents
# with bare numbers on them. GBP remains the default for every
# existing and new workspace.
SUPPORTED_CURRENCIES = frozenset({"GBP", "EUR", "USD"})


class TenantCreate(BaseModel):
    name: str
    # Auto-generated from `name` by TenantService.create() if omitted — see
    # app/tenants/service.py's _slugify().
    slug: str | None = None


class TenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: str
    created_at: datetime


# Sprint 034 — the customer-facing company identity. Split out from
# TenantOut so the same field set can be reused by the PATCH body (all
# optional, PATCH semantics) and by the read model, without either one
# drifting from the other.
class TenantIdentityFields(BaseModel):
    legal_name: str | None = None
    trading_name: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    postcode: str | None = None
    country: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    website: str | None = None
    company_number: str | None = None
    # Nullable on purpose: not every UK business is VAT-registered, and an
    # invented VAT number on an invoice is a legal defect, not a cosmetic
    # one. Absent means "not registered / not supplied", never a placeholder.
    vat_number: str | None = None
    logo_url: str | None = None
    document_footer: str | None = None


class TenantProfileUpdate(TenantIdentityFields):
    """PATCH body. Every field optional; only fields actually present in the
    request are written (see TenantService.update_identity)."""

    # The workspace name staff see in-product. Editable here too so an
    # owner who signed up as "Default Workspace" can correct it.
    name: str | None = None

    # Sprint 036 — workspace configuration. `currency` is validated
    # against a short supported list rather than accepting any three
    # letters: an unrecognised code would render amounts with no symbol
    # and no meaning on a customer-facing document.
    currency: str | None = None

    @field_validator("currency")
    @classmethod
    def _supported_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalised = value.strip().upper()
        if normalised not in SUPPORTED_CURRENCIES:
            raise ValueError(
                f"currency must be one of {sorted(SUPPORTED_CURRENCIES)}"
            )
        return normalised


class TenantProfileOut(TenantIdentityFields):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: str
    created_at: datetime

    # Sprint 036
    currency: str
    # A comma-separated key list on the row; exposed to clients as a real
    # list so no consumer has to know the storage format.
    trades: list[str] = []
    onboarding_completed_at: datetime | None = None
    # True when an uploaded logo file exists for this tenant. The file is
    # served by its own endpoint rather than by URL, so this is a flag,
    # not a path — the storage filename is never exposed to a client.
    has_uploaded_logo: bool = False


class TenantOnboardingUpdate(BaseModel):
    """Sprint 036 (Workstream J) — what the onboarding flow collects.

    Separate from TenantProfileUpdate because it answers a different
    question: not "what are this company's statutory details" but "what
    does this business do, and is it set up yet". Keeping them apart means
    completing onboarding can never accidentally clear a VAT number.
    """

    trades: list[str] | None = None
    currency: str | None = None
    complete: bool = False

    @field_validator("trades")
    @classmethod
    def _known_trades(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        unknown = [key for key in value if key not in TRADE_KEYS]
        if unknown:
            raise ValueError(f"unknown trade(s): {sorted(unknown)}")
        return value

    @field_validator("currency")
    @classmethod
    def _supported_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalised = value.strip().upper()
        if normalised not in SUPPORTED_CURRENCIES:
            raise ValueError(f"currency must be one of {sorted(SUPPORTED_CURRENCIES)}")
        return normalised


class OnboardingStateOut(BaseModel):
    """Whether this workspace still needs setting up.

    `required` is deliberately computed rather than read straight from
    `onboarding_completed_at`: every tenant that existed before Sprint 036
    has a NULL there, and sending an established business — one with real
    customers, quotes and projects — back to a setup wizard would be a
    regression dressed as a feature. See TenantService.onboarding_state.
    """

    required: bool
    completed_at: datetime | None
    trades: list[str]
    currency: str
    has_company_identity: bool
    has_team_invitations: bool
    workspace_has_data: bool

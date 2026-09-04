import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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


class TenantProfileOut(TenantIdentityFields):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    status: str
    created_at: datetime

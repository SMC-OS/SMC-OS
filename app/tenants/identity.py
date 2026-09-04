"""Resolving a tenant's customer-facing company identity (Sprint 034).

Before this sprint app/quotes/pdf.py hardcoded one company's letterhead
into every PDF the platform produced, for every tenant. This module is the
single place that answers "whose business details go on this document?",
and the answer is always: the tenant that owns the document.

Three rules this module exists to enforce:

1. **Never the platform's brand.** GeoCore (and "SIMO OS" before it) is the
   product a tenant subscribes to, not the business a tenant's customer is
   buying from. No platform name is ever rendered as a trading identity on
   a tenant's quote or invoice.
2. **Never another tenant's details.** A tenant with nothing configured
   falls back to its own workspace `name`, not to a global default.
3. **Never a fabricated statutory number.** `company_number`/`vat_number`
   render only when the tenant has actually supplied them. An absent VAT
   number means the VAT line is labelled without a registration, not with a
   made-up one.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CompanyIdentity:
    """The subset of a tenant's profile that appears on a customer-facing
    document. Deliberately a plain value object, not an ORM row — the PDF
    layer never touches the database or a Session."""

    display_name: str
    legal_name: str | None = None
    address_lines: tuple[str, ...] = field(default_factory=tuple)
    contact_lines: tuple[str, ...] = field(default_factory=tuple)
    registration_lines: tuple[str, ...] = field(default_factory=tuple)
    logo_url: str | None = None
    document_footer: str | None = None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _lines(*values: str | None) -> tuple[str, ...]:
    return tuple(cleaned for cleaned in (_clean(v) for v in values) if cleaned is not None)


def resolve(tenant) -> CompanyIdentity:
    """Map a Tenant row onto the identity its documents render.

    `tenant` may be None (an anonymous/unlinked quote, which stays possible
    by ADR-023) — the caller gets a neutral identity rather than an
    exception, and certainly rather than some other tenant's letterhead.
    """
    if tenant is None:
        return CompanyIdentity(display_name="")

    legal_name = _clean(getattr(tenant, "legal_name", None))
    trading_name = _clean(getattr(tenant, "trading_name", None))
    workspace_name = _clean(getattr(tenant, "name", None))

    # What the customer sees at the top: the trading name they'd recognise,
    # else the registered legal name, else the workspace name the tenant
    # signed up with. There is no fourth fallback by design.
    display_name = trading_name or legal_name or workspace_name or ""

    # Only repeat the legal entity separately when it genuinely differs
    # from the displayed trading name — "Trading As" lines that just echo
    # the heading are noise on an invoice.
    secondary_legal = legal_name if legal_name and legal_name != display_name else None

    city_line = ", ".join(_lines(getattr(tenant, "city", None), getattr(tenant, "postcode", None)))

    address_lines = _lines(
        getattr(tenant, "address_line1", None),
        getattr(tenant, "address_line2", None),
        city_line or None,
        getattr(tenant, "country", None),
    )

    contact_lines = _lines(
        getattr(tenant, "contact_phone", None),
        getattr(tenant, "contact_email", None),
        getattr(tenant, "website", None),
    )

    company_number = _clean(getattr(tenant, "company_number", None))
    vat_number = _clean(getattr(tenant, "vat_number", None))
    registration_lines = _lines(
        f"Company registration no. {company_number}" if company_number else None,
        f"VAT registration no. {vat_number}" if vat_number else None,
    )

    return CompanyIdentity(
        display_name=display_name,
        legal_name=secondary_legal,
        address_lines=address_lines,
        contact_lines=contact_lines,
        registration_lines=registration_lines,
        logo_url=_clean(getattr(tenant, "logo_url", None)),
        document_footer=_clean(getattr(tenant, "document_footer", None)),
    )

"""Invoice supplier settings: validation and the frozen snapshot (release default).

A document is issued as an invoice on its first download (that is when its number is allocated). At that moment
the workspace's supplier identity, VAT status and payment details are validated against the workspace's own legal
and VAT status and then frozen onto the quote, so a later settings change can never alter an issued document.
Nothing here invents company information: a missing field is reported, never filled.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.tenants import identity as tenant_identity


class InvoiceSupplierIncomplete(Exception):
    def __init__(self, missing: list[dict]):
        self.missing = missing
        super().__init__("; ".join(m["message"] for m in missing))


def _has(value) -> bool:
    return bool(value and str(value).strip())


def validate(tenant, vat_amount: float | None) -> list[dict]:
    """Return the problems that stop this workspace issuing a compliant invoice (empty = fine)."""
    problems: list[dict] = []

    def need(code, message):
        problems.append({"field": code, "message": message})

    if not _has(tenant.legal_name):
        need("legal_name", "Legal business name is required")
    if not _has(tenant.address_line1) or not _has(tenant.postcode):
        need("address", "Registered or business address (first line and postcode) is required")
    if tenant.vat_registered:
        if not _has(tenant.vat_number):
            need("vat_number", "A VAT-registered business must record its VAT registration number")
    elif (vat_amount or 0) > 0:
        need("vat_registered", "This workspace is not marked VAT-registered but the document charges VAT; record the VAT registration or use 0% VAT")
    elif _has(tenant.vat_number):
        need("vat_registered", "A VAT number is recorded but the workspace is not marked VAT-registered")
    bank_complete = _has(tenant.bank_account_name) and _has(tenant.bank_sort_code) and _has(tenant.bank_account_number)
    if not bank_complete and not _has(tenant.payment_instructions):
        need("payment_details", "Bank details (name, sort code, account number) or payment instructions are required")
    if tenant.payment_terms_days is None:
        need("payment_terms_days", "Payment terms are required")
    return problems


def build_snapshot(tenant, issued_at: datetime) -> dict:
    ident = tenant_identity.resolve(tenant)
    terms = int(tenant.payment_terms_days if tenant.payment_terms_days is not None else 30)
    due = (issued_at.astimezone(timezone.utc).date() + timedelta(days=terms)).isoformat()
    return {
        "identity": {
            "display_name": ident.display_name, "legal_name": ident.legal_name,
            "address_lines": list(ident.address_lines), "contact_lines": list(ident.contact_lines),
            "registration_lines": list(ident.registration_lines), "logo_url": ident.logo_url,
            "document_footer": ident.document_footer,
        },
        "vat_registered": bool(tenant.vat_registered),
        "payment": {
            "account_name": tenant.bank_account_name, "sort_code": tenant.bank_sort_code,
            "account_number": tenant.bank_account_number, "instructions": tenant.payment_instructions,
            "terms_days": terms,
        },
        "issued_at": issued_at.isoformat(),
        "due_date": due,
    }


def identity_from_snapshot(snapshot: dict) -> tenant_identity.CompanyIdentity:
    i = snapshot["identity"]
    return tenant_identity.CompanyIdentity(
        display_name=i["display_name"], legal_name=i.get("legal_name"), address_lines=tuple(i.get("address_lines", ())),
        contact_lines=tuple(i.get("contact_lines", ())), registration_lines=tuple(i.get("registration_lines", ())),
        logo_url=i.get("logo_url"), document_footer=i.get("document_footer"),
    )


def due_date_from_snapshot(snapshot: dict) -> date:
    return date.fromisoformat(snapshot["due_date"])

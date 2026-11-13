"""Allocate stable per-workspace invoice references under a database lock, and freeze the supplier snapshot."""
from datetime import datetime, timezone

from sqlalchemy import select

from app.database.models import Quote, Tenant
from app.tenants import invoice_supplier


def issue_invoice(db, quote):
    """Return (reference, snapshot). The first call issues the invoice: validates the workspace's supplier settings,
    allocates the next number and freezes the snapshot. Later calls return the stored values unchanged."""
    # Serialises both concurrent first downloads and sequence-setting changes.
    tenant = db.scalar(select(Tenant).where(Tenant.id == quote.tenant_id).with_for_update().execution_options(populate_existing=True))
    if tenant is None:
        raise ValueError("Invoice requires a workspace")
    db.refresh(quote)
    if quote.invoice_number:
        return quote.invoice_number, quote.invoice_snapshot
    problems = invoice_supplier.validate(tenant, quote.vat)
    if problems:
        db.rollback()
        raise invoice_supplier.InvoiceSupplierIncomplete(problems)
    number = tenant.invoice_next_number
    prefix = tenant.invoice_prefix.strip()
    while db.scalar(select(Quote.id).where(Quote.tenant_id == tenant.id, Quote.invoice_number == f"{prefix}-{number:06d}")) is not None:
        number += 1
    issued_at = datetime.now(timezone.utc)
    snapshot = invoice_supplier.build_snapshot(tenant, issued_at)
    quote.invoice_number = f"{prefix}-{number:06d}"
    quote.invoice_issued_at = issued_at
    quote.invoice_due_date = invoice_supplier.due_date_from_snapshot(snapshot)
    quote.invoice_snapshot = snapshot
    tenant.invoice_next_number = number + 1
    db.flush()
    return quote.invoice_number, quote.invoice_snapshot


def invoice_reference(db, quote):
    """The stable reference only (issues the invoice on first use)."""
    return issue_invoice(db, quote)[0]

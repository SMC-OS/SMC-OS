"""Allocate stable per-workspace invoice references under a database lock."""
from sqlalchemy import select
from app.database.models import Quote, Tenant

def invoice_reference(db, quote):
    # Serialises both concurrent first downloads and sequence-setting changes.
    tenant = db.scalar(select(Tenant).where(Tenant.id == quote.tenant_id).with_for_update().execution_options(populate_existing=True))
    if tenant is None:
        raise ValueError("Invoice requires a workspace")
    db.refresh(quote)
    if quote.invoice_number:
        return quote.invoice_number
    number = tenant.invoice_next_number
    prefix = tenant.invoice_prefix.strip()
    while db.scalar(select(Quote.id).where(Quote.tenant_id == tenant.id, Quote.invoice_number == f"{prefix}-{number:06d}")) is not None:
        number += 1
    quote.invoice_number = f"{prefix}-{number:06d}"
    tenant.invoice_next_number = number + 1
    db.flush()
    return quote.invoice_number

"""Sprint 013 (docs/DECISIONS.md ADR-030).

No router-level `dependencies=[...]` (same shape app/invitations/router.py
and app/auth/router.py already use): this router genuinely mixes
authenticated management routes and one fully public route. Auth is
applied per-route below.

Creation is deliberately NOT require_role(OWNER)-gated, unlike inviting a
teammate (ADR-028) — sharing a project link with a customer is routine
Staff work, not a tenant-control decision, so any authenticated user of
the tenant can create/list/revoke a portal link.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.customers.service import customer_service
from app.database.database import get_db
from app.database.models import User
from app.documents.models import DocumentOut
from app.documents.service import document_service
from app.messages.models import MessageOut
from app.portal.models import (
    PortalLinkCreate,
    PortalLinkCreateOut,
    PortalLinkOut,
    PortalMessageCreate,
    PortalProjectOut,
    PortalPublicOut,
    PortalQuoteOut,
)
from app.portal.service import (
    CustomerNotFoundError,
    PortalLinkNotFoundError,
    portal_service,
)
from app.quotes.pdf import PDFGenerator, build_line_items
from app.tenants import identity as tenant_identity
from app.tenants.service import tenant_service

router = APIRouter(prefix="/portal-links", tags=["portal"])


@router.post("", response_model=PortalLinkCreateOut, status_code=status.HTTP_201_CREATED)
def create_portal_link(
    data: PortalLinkCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        row, raw_token = portal_service.create_link(
            db,
            tenant_id=current_user.tenant_id,
            created_by_user_id=current_user.id,
            customer_id=data.customer_id,
        )
    except CustomerNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return PortalLinkCreateOut(**PortalLinkOut.model_validate(row).model_dump(), token=raw_token)


@router.get("", response_model=list[PortalLinkOut])
def list_portal_links(
    customer_id: uuid.UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = portal_service.list_links(db, current_user.tenant_id, customer_id=customer_id)
    out = []
    for row in rows:
        item = PortalLinkOut.model_validate(row)
        item.status = portal_service.derive_status(row)
        out.append(item)
    return out


@router.delete("/{portal_link_id}", response_model=PortalLinkOut)
def revoke_portal_link(
    portal_link_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return portal_service.revoke_link(db, current_user.tenant_id, portal_link_id)
    except PortalLinkNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal link not found")


@router.get("/token/{token}", response_model=PortalPublicOut)
def get_portal_by_token(token: str, db: Session = Depends(get_db)):
    try:
        row, link_status, tenant, customer, projects, quotes = portal_service.get_public_view(db, token)
    except PortalLinkNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal link not found")
    return PortalPublicOut(
        status=link_status,
        tenant_name=tenant.name if tenant is not None else "",
        customer_name=customer.name if customer is not None else "",
        expires_at=row.expires_at,
        projects=[PortalProjectOut.model_validate(p) for p in projects],
        quotes=[PortalQuoteOut.model_validate(q) for q in quotes],
    )


@router.get("/token/{token}/invoice/{quote_id}")
def download_portal_invoice(token: str, quote_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        quote = portal_service.get_customer_quote(db, token, quote_id)
    except PortalLinkNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")

    customer = customer_service.get(db, quote.customer_id, tenant_id=quote.tenant_id)
    customer_name = customer.name if customer is not None else "No customer linked"

    pdf_bytes = PDFGenerator().create(
        {
            "id": quote.id,
            "customer": customer_name,
            # Sprint 034 — the customer downloading this over a portal link
            # sees the identity of the tenant that issued the quote, keyed
            # off the quote's own tenant_id rather than any caller context
            # (there is no authenticated user on a portal route).
            "company": tenant_identity.resolve(tenant_service.get(db, quote.tenant_id)),
            "line_items": build_line_items(quote),
            "price_before_vat": quote.price_before_vat,
            "vat": quote.vat,
            "total": quote.total,
            "created_at": quote.created_at,
        }
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="invoice-{str(quote.id)[:8]}.pdf"'
        },
    )


@router.get("/token/{token}/documents", response_model=list[DocumentOut])
def list_portal_documents(token: str, db: Session = Depends(get_db)):
    try:
        return portal_service.list_customer_documents(db, token)
    except PortalLinkNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal link not found")


@router.get("/token/{token}/documents/{document_id}/download")
def download_portal_document(token: str, document_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        row = portal_service.get_customer_document(db, token, document_id)
    except PortalLinkNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return FileResponse(
        path=document_service.file_path(row),
        media_type=row.content_type,
        filename=row.original_filename,
    )


@router.get("/token/{token}/messages", response_model=list[MessageOut])
def list_portal_messages(token: str, db: Session = Depends(get_db)):
    try:
        return portal_service.list_customer_messages(db, token)
    except PortalLinkNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal link not found")


@router.post("/token/{token}/messages", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
def post_portal_message(token: str, data: PortalMessageCreate, db: Session = Depends(get_db)):
    try:
        return portal_service.post_customer_message(db, token, data.body)
    except PortalLinkNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portal link not found")

"""Purchase order PDF — GeoCore Premium OS Plan 05 (Sprint 044).

Reuses app/tenants/identity.py's CompanyIdentity resolution and the same
reportlab table styling app/quotes/pdf.py and app/variations/pdf.py
already established — never a hardcoded letterhead; the issuing tenant's
own identity, resolved fresh per document. Its own small renderer, same
reasoning as app/variations/pdf.py: a PurchaseOrderItem is not
QuoteItem-shaped, but the document shape (letterhead, title, VAT
breakdown table) is identical.
"""

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.quotes.pdf import _CURRENCY_SYMBOLS, _escape
from app.tenants.identity import CompanyIdentity


def build_purchase_order_pdf(purchase_order, items, *, project, supplier, tenant) -> bytes:
    from app.tenants.identity import resolve as resolve_identity

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
    styles = getSampleStyleSheet()
    story = []

    company = resolve_identity(tenant) if tenant is not None else CompanyIdentity(display_name="")
    if company.display_name:
        story.append(Paragraph(_escape(company.display_name.upper()), styles["Heading1"]))
    if company.legal_name:
        story.append(Paragraph(_escape(company.legal_name), styles["Normal"]))
    for line in company.address_lines:
        story.append(Paragraph(_escape(line), styles["Normal"]))
    for line in company.contact_lines:
        story.append(Paragraph(_escape(line), styles["Normal"]))
    for line in company.registration_lines:
        story.append(Paragraph(_escape(line), styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph(_escape(f"Purchase Order {purchase_order.reference}"), styles["Heading2"]))
    if supplier is not None:
        story.append(Paragraph(f"Supplier: {_escape(supplier.name)}", styles["Normal"]))
    if project is not None:
        story.append(Paragraph(f"Project: {_escape(project.name)}", styles["Normal"]))
    story.append(Paragraph(f"Date: {purchase_order.created_at:%d %B %Y}", styles["Normal"]))
    if purchase_order.expected_delivery_date:
        story.append(
            Paragraph(f"Expected delivery: {purchase_order.expected_delivery_date:%d %B %Y}", styles["Normal"])
        )
    story.append(Paragraph(f"Status: {_escape(purchase_order.status.replace('_', ' ').title())}", styles["Normal"]))
    if purchase_order.notes:
        story.append(Spacer(1, 8))
        story.append(Paragraph(_escape(purchase_order.notes), styles["Normal"]))
    story.append(Spacer(1, 16))

    symbol = _CURRENCY_SYMBOLS.get((tenant.currency if tenant is not None else None) or "GBP", "")

    def money(amount: float) -> str:
        return f"{symbol}{amount:,.2f}"

    rows = [["Description", "Qty", "Unit cost", "Amount"]]
    rows += [
        [item.description, f"{item.quantity:g}", money(item.unit_cost), money(item.line_total)]
        for item in items
    ]
    rows += [
        ["", "", "Subtotal", money(purchase_order.subtotal)],
        ["", "", f"VAT ({purchase_order.vat_rate * 100:g}%)", money(purchase_order.vat)],
        ["", "", "Total", money(purchase_order.total)],
    ]
    table = Table(rows, colWidths=[80 * mm, 20 * mm, 35 * mm, 35 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)

    if company.document_footer:
        story.append(Spacer(1, 16))
        story.append(Paragraph(_escape(company.document_footer), styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()

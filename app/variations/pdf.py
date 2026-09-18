"""Variation (change order) PDF — GeoCore Premium OS Plan 04 (Sprint 043).

Reuses app/tenants/identity.py's CompanyIdentity resolution and the same
reportlab table styling app/quotes/pdf.py established (Sprint 034) —
never SMC's or any other hardcoded letterhead; the issuing tenant's own
identity, resolved fresh per document, exactly like an invoice.

Deliberately its own small renderer rather than reusing
app/quotes/pdf.py's PDFGenerator class directly: that class's
build_line_items() reads QuoteItem-shaped rows (item_type, material,
thickness, ...), which a VariationItem does not have. The document
shape a customer sees — letterhead, title, VAT breakdown table — is the
same; only the row source differs.
"""

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.quotes.pdf import _CURRENCY_SYMBOLS, _escape
from app.tenants.identity import CompanyIdentity


def build_variation_pdf(variation, items, *, project, customer, tenant) -> bytes:
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

    story.append(Paragraph(_escape(f"Variation {variation.reference}"), styles["Heading2"]))
    story.append(Paragraph(_escape(variation.title), styles["Normal"]))
    if project is not None:
        story.append(Paragraph(f"Project: {_escape(project.name)}", styles["Normal"]))
    if customer is not None:
        story.append(Paragraph(f"Customer: {_escape(customer.name)}", styles["Normal"]))
    story.append(Paragraph(f"Date: {variation.created_at:%d %B %Y}", styles["Normal"]))
    story.append(Paragraph(f"Status: {_escape(variation.status.title())}", styles["Normal"]))
    if variation.description:
        story.append(Spacer(1, 8))
        story.append(Paragraph(_escape(variation.description), styles["Normal"]))
    story.append(Spacer(1, 16))

    symbol = _CURRENCY_SYMBOLS.get((tenant.currency if tenant is not None else None) or "GBP", "")

    def money(amount: float) -> str:
        return f"{symbol}{amount:,.2f}"

    rows = [["Description", "Qty", "Unit price", "Amount"]]
    rows += [
        [item.description, f"{item.quantity:g}", money(item.unit_price), money(item.line_total)]
        for item in items
    ]
    rows += [
        ["", "", "Subtotal", money(variation.subtotal)],
        ["", "", f"VAT ({variation.vat_rate * 100:g}%)", money(variation.vat)],
        ["", "", "Total", money(variation.total)],
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

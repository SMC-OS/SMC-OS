"""Invoice PDF generation (Sprint 007).

Rewritten from the Sprint 001 stub: proper letterhead, a real VAT
breakdown table, generated to an in-memory buffer (not quote.pdf on local
disk) so it can be returned directly as a downloadable HTTP response —
see app/quotes/router.py's GET /quotes/{id}/invoice.
"""

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def build_line_items(quote) -> list[dict]:
    """One invoice row per QuoteItem (Sprint 033) — shared by
    app/quotes/router.py and app/portal/router.py so a quote's real
    line-by-line content, not a collapsed single material/thickness
    summary, is what a customer actually sees on the PDF."""
    return [
        {
            "description": (
                f"{item.item_type.replace('_', ' ').title()} — {item.material} "
                f"({item.thickness}), {item.quantity} x {item.length_mm:g}mm x {item.width_mm:g}mm"
            ),
            "amount": item.line_total if item.line_total is not None else 0.0,
        }
        for item in quote.items
    ]


class PDFGenerator:
    def create(self, invoice: dict) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
        )
        styles = getSampleStyleSheet()
        story = []

        # Letterhead
        story.append(Paragraph("SIMO MARBLE &amp; CONSTRUCTION LTD", styles["Heading1"]))
        story.append(Paragraph("Unit 4, Riverside Trade Park, London", styles["Normal"]))
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"Invoice for Quote #{str(invoice['id'])[:8]}", styles["Heading2"]))
        story.append(Paragraph(f"Date: {invoice['created_at']:%d %B %Y}", styles["Normal"]))
        story.append(Paragraph(f"Customer: {invoice['customer']}", styles["Normal"]))
        story.append(Spacer(1, 16))

        # VAT breakdown table — one row per line item (Sprint 033), then
        # VAT/Total. Falls back to the old single material/thickness row
        # if a caller hasn't been updated to pass `line_items` yet.
        line_items = invoice.get("line_items") or [
            {
                "description": f"{invoice['material']} ({invoice['thickness']})",
                "amount": invoice["price_before_vat"],
            }
        ]
        rows = [["Description", "Amount"]]
        rows += [[item["description"], f"£{item['amount']:,.2f}"] for item in line_items]
        rows += [
            ["VAT (20%)", f"£{invoice['vat']:,.2f}"],
            ["Total", f"£{invoice['total']:,.2f}"],
        ]
        table = Table(rows, colWidths=[110 * mm, 50 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                    ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                    ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(table)

        doc.build(story)
        return buffer.getvalue()

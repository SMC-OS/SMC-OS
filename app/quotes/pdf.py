"""Invoice PDF generation (Sprint 007, tenant-aware since Sprint 034).

Rewritten from the Sprint 001 stub: proper letterhead, a real VAT
breakdown table, generated to an in-memory buffer (not quote.pdf on local
disk) so it can be returned directly as a downloadable HTTP response —
see app/quotes/router.py's GET /quotes/{id}/invoice.

Sprint 034 removed the hardcoded letterhead. This module now renders
whatever CompanyIdentity its caller hands it and holds no company name,
address, or registration number of its own — see app/tenants/identity.py
for how one is resolved from a Tenant row, and why the platform's own
brand is never a candidate.
"""

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.tenants.identity import CompanyIdentity
from app.trades import units

# Rendered next to every amount on the document. Deliberately a small
# explicit map rather than a locale library: a PDF has no browser Intl to
# call, and adding a dependency to print three symbols would be
# disproportionate. An unmapped currency renders bare amounts, with the
# code stated once under the heading, rather than a wrong symbol.
_CURRENCY_SYMBOLS = {"GBP": "\u00a3", "EUR": "\u20ac", "USD": "$"}


def _describe_stone_item(item) -> str:
    """A slab line, described the way it has been described since Sprint
    033. Kept byte-for-byte so an existing quote's PDF renders exactly as
    it did before Sprint 036 — a customer comparing an old printout with a
    re-download must not see a different document.

    Each part is guarded because Sprint 036 made these columns nullable
    for general quotes; a stone line still always has them, but the
    function must not raise if it ever meets a half-populated row.
    """
    parts = [item.item_type.replace("_", " ").title()]
    if item.material:
        material = item.material
        if item.thickness:
            material = f"{material} ({item.thickness})"
        parts.append(material)
    label = " — ".join(parts)

    if item.length_mm is not None and item.width_mm is not None:
        label += f", {item.quantity:g} x {item.length_mm:g}mm x {item.width_mm:g}mm"
    return label


def _describe_general_item(item, symbol: str) -> str:
    """A general construction line: what it is, how much of it, and at
    what rate — "Strip out existing bathroom, 2.5 day @ £320.00".

    The rate is shown because a construction customer expects to see it,
    and because a quote whose lines cannot be checked against its total is
    a quote that generates phone calls. The symbol is passed in from the
    quote's own stored currency rather than hardcoded, for the same
    reason the totals table takes one.
    """
    label = item.description or "Line item"
    unit_label = units.label_for(item.unit) or item.unit or "item"
    if item.unit_price is not None:
        return f"{label}, {item.quantity:g} {unit_label} @ {symbol}{item.unit_price:,.2f}"
    return f"{label}, {item.quantity:g} {unit_label}"


def build_line_items(quote) -> list[dict]:
    """One invoice row per QuoteItem (Sprint 033) — shared by
    app/quotes/router.py and app/portal/router.py so a quote's real
    line-by-line content, not a collapsed single material/thickness
    summary, is what a customer actually sees on the PDF.

    Sprint 036: a quote's lines can now be slabs or general construction
    lines, and the two are described differently because they genuinely
    are different things. The branch is on the line's own `line_kind`, not
    on the quote's kind, so a future quote mixing a worktop with two days
    of fitting labour renders both correctly with no further change here.
    """
    symbol = _CURRENCY_SYMBOLS.get(getattr(quote, "currency", None) or "GBP", "")
    return [
        {
            "description": (
                _describe_stone_item(item)
                if item.line_kind == "stone"
                else _describe_general_item(item, symbol)
            ),
            "amount": item.line_total if item.line_total is not None else 0.0,
        }
        for item in quote.items
    ]


def _escape(value: str) -> str:
    """ReportLab paragraphs are mini-HTML, so tenant-supplied text has to be
    escaped — "Simo Marble & Construction Ltd" is a perfectly ordinary
    company name that would otherwise abort the render on a bad entity."""
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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

        # Letterhead — the issuing tenant's own business identity. A caller
        # that passes none gets a document with no letterhead at all, which
        # is the correct failure: an unattributed invoice is recoverable,
        # one carrying the wrong company's name is not.
        company = invoice.get("company") or CompanyIdentity(display_name="")
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
        # A general quote carries a real job title ("Bathroom refit,
        # 14 Elm Road"); a stone quote never had one, and keeps the exact
        # heading it has had since Sprint 007 so a re-downloaded historical
        # document is identical to the one the customer already holds.
        heading = invoice.get("title") or f"Invoice for Quote #{str(invoice['id'])[:8]}"
        story.append(Paragraph(_escape(str(heading)), styles["Heading2"]))
        currency = invoice.get("currency") or "GBP"
        if currency not in _CURRENCY_SYMBOLS:
            story.append(Paragraph(f"All amounts in {_escape(currency)}", styles["Normal"]))
        story.append(Paragraph(f"Date: {invoice['created_at']:%d %B %Y}", styles["Normal"]))
        story.append(Paragraph(f"Customer: {_escape(invoice['customer'])}", styles["Normal"]))
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
        # Sprint 036 — the document is denominated in the quote's own
        # stored currency, not in a hardcoded pound sign, and the VAT row
        # is labelled with the rate that was actually applied to this
        # quote rather than an assumed 20%. Both fall back to the previous
        # behaviour when a caller hasn't been updated, so an existing
        # caller's output is unchanged.
        symbol = _CURRENCY_SYMBOLS.get(invoice.get("currency") or "GBP", "")
        vat_rate = invoice.get("vat_rate")
        vat_label = (
            f"VAT ({vat_rate * 100:g}%)" if vat_rate is not None else "VAT (20%)"
        )

        def money(amount: float) -> str:
            return f"{symbol}{amount:,.2f}"

        rows = [["Description", "Amount"]]
        rows += [[item["description"], money(item["amount"])] for item in line_items]

        # A discount is shown as its own row rather than folded silently
        # into the line items: a customer who was given £250 off should be
        # able to see that they were.
        discount = invoice.get("discount_amount") or 0
        if discount:
            rows.append(["Discount", f"-{money(discount)}"])

        rows += [
            [vat_label, money(invoice["vat"])],
            ["Total", money(invoice["total"])],
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

        if company.document_footer:
            story.append(Spacer(1, 16))
            story.append(Paragraph(_escape(company.document_footer), styles["Normal"]))

        doc.build(story)
        return buffer.getvalue()

from reportlab.platypus import SimpleDocTemplate
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet

class PDFGenerator:

    def create(self, quote):

        pdf = SimpleDocTemplate("quote.pdf")
    

        styles = getSampleStyleSheet()

        story = []

        story.append(Paragraph("SIMO MARBLE & CONSTRUCTION LTD", styles["Heading1"]))

        story.append(Paragraph(f"Customer: {quote['customer']}", styles["Normal"]))

        story.append(Paragraph(f"Material: {quote['material']}", styles["Normal"]))

        story.append(Paragraph(f"Total: £{quote['total']}", styles["Heading2"]))

        pdf.build(story)

        return "quote.pdf"
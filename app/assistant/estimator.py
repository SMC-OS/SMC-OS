import re

class EstimatorAssistant:
    """Legacy regex-based /estimate path (Sprint 001). Deliberately not
    upgraded with the natural-language dimension parsing Sprint 032 adds
    to the AI Quotation Generator (app/quotes/ai_draft.py) — this endpoint
    stays a crude fallback; the AI draft flow is the supported path for
    natural-language quote creation. Only adapted here to keep emitting a
    valid QuoteRequest under the new structured-dimension schema (Sprint
    032, Workstream C) — the first number found is still treated as
    metres, matching its historical behaviour exactly.
    """

    def parse(self, text):

        quote = {
            "customer": "Unknown",
            "material": None,
            "length_mm": 0.0,
            "unit_input": "m",
            "thickness": "20mm",
            "island": False,
            "waterfall": 0,
            "splashback": False,
            "upstands": False,
        }

        text = text.lower()

        if "calacatta oro" in text:
            quote["material"] = "Calacatta Oro"

        if "calacatta gold" in text:
            quote["material"] = "Calacatta Gold"

        if "nero marquina" in text:
            quote["material"] = "Nero Marquina"

        numbers = re.findall(r"\d+\.?\d*", text)

        if numbers:
            quote["length_mm"] = float(numbers[0]) * 1000

        if "island" in text:
            quote["island"] = True

        if "waterfall" in text:
            quote["waterfall"] = 1

        if "splashback" in text:
            quote["splashback"] = True
            quote["splashback_length_mm"] = quote["length_mm"]

        if "upstand" in text:
            quote["upstands"] = True
            quote["upstands_length_mm"] = quote["length_mm"]

        return quote

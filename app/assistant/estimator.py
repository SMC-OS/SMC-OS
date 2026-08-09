import re

class EstimatorAssistant:

    def parse(self, text):

        quote = {
            "customer": "Unknown",
            "material": None,
            "kitchen_length": 0,
            "thickness": "20mm",
            "island": False,
            "waterfall": 0,
            "splashback": False,
            "upstands": False
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
            quote["kitchen_length"] = float(numbers[0])

        if "island" in text:
            quote["island"] = True

        if "waterfall" in text:
            quote["waterfall"] = 1

        if "splashback" in text:
            quote["splashback"] = True

        if "upstand" in text:
            quote["upstands"] = True

        return quote
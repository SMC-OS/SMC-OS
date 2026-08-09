from app.data.materials import MATERIALS
from app.data.pricing import PRICES
from app.data.services import SERVICES


class SalesAssistant:

    def reply(self, text: str):

        text = text.lower()

        for material in MATERIALS:

            if material in text:

                return {
                    "material": material.title(),
                    "price": f"£{PRICES[material]}",
                    "details": MATERIALS[material],
                    "includes": SERVICES
                }

        return {
            "message": "I couldn't find that material."
        }
from app.data.materials import MATERIALS
from app.data.pricing import PRICES


class SearchAssistant:

    def search(self, text: str):

        text = text.lower()

        results = []

        for material, info in MATERIALS.items():

            score = 0

            if material in text:
                score += 5

            if info["category"].lower() in text:
                score += 2

            if info["finish"].lower() in text:
                score += 1

            for thickness in info["thickness"]:
                if thickness.lower() in text:
                    score += 1

            if score > 0:
                results.append({
                    "material": material.title(),
                    "price": PRICES[material],
                    "details": info,
                    "score": score
                })

        results.sort(key=lambda x: x["score"], reverse=True)

        return results
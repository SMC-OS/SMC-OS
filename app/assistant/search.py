from sqlalchemy.orm import Session

from app.materials.service import material_service


class SearchAssistant:

    def search(self, db: Session, text: str):

        text = text.lower()

        results = []

        for material in material_service.list_all(db):

            score = 0

            if material.name.lower() in text:
                score += 5

            if material.category and material.category.lower() in text:
                score += 2

            if material.finish and material.finish.lower() in text:
                score += 1

            if material.thickness and material.thickness.lower() in text:
                score += 1

            if score > 0:
                results.append({
                    "material": material.name,
                    "price": material.price,
                    "details": {
                        "category": material.category,
                        "thickness": material.thickness,
                        "slab_size": material.slab_size,
                        "finish": material.finish,
                    },
                    "score": score
                })

        results.sort(key=lambda x: x["score"], reverse=True)

        return results

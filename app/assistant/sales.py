from sqlalchemy.orm import Session

from app.data.services import SERVICES
from app.materials.search import material_search_service


class SalesAssistant:
    """Pricing-oriented reply over MaterialSearchService — the canonical,
    deterministic material retrieval path (Sprint 032, Workstream B). This
    class must never reimplement matching logic itself.
    """

    def reply(self, db: Session, text: str):
        result = material_search_service.search(db, text)

        if result.status == "found":
            m = result.material
            return {
                "material": m.name,
                "price": f"£{m.price}",
                "details": {
                    "category": m.category,
                    "thickness": m.thickness,
                    "slab_size": m.slab_size,
                    "finish": m.finish,
                },
                "includes": SERVICES,
            }

        if result.status == "multiple":
            return {
                "message": "I found more than one matching material — which one did you mean?",
                "candidates": [
                    {
                        "material": match.material.name,
                        "thickness": match.material.thickness,
                        "price": f"£{match.material.price}",
                    }
                    for match in result.matches
                ],
            }

        return {"message": "I couldn't find that material."}

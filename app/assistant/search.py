from sqlalchemy.orm import Session

from app.materials.search import material_search_service


class SearchAssistant:
    """Thin presentation layer over MaterialSearchService — the canonical,
    deterministic material retrieval path (Sprint 032, Workstream B). This
    class must never reimplement matching logic; it only shapes the
    service's FOUND/MULTIPLE/NOT_FOUND result for the /process response.
    """

    def search(self, db: Session, text: str):
        result = material_search_service.search(db, text)

        def _shape(match):
            m = match.material
            return {
                "material": m.name,
                "price": m.price,
                "details": {
                    "category": m.category,
                    "thickness": m.thickness,
                    "slab_size": m.slab_size,
                    "finish": m.finish,
                },
            }

        if result.status == "found":
            return {"status": "found", "result": _shape(result.matches[0])}

        if result.status == "multiple":
            return {
                "status": "multiple",
                "results": [_shape(m) for m in result.matches],
            }

        return {
            "status": "not_found",
            "message": "No matching product was found in the GeoCore catalogue.",
        }

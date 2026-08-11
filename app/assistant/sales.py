from sqlalchemy.orm import Session

from app.data.services import SERVICES
from app.materials.service import material_service


class SalesAssistant:

    def reply(self, db: Session, text: str):

        text = text.lower()

        for material in material_service.list_all(db):

            if material.name.lower() in text:

                return {
                    "material": material.name,
                    "price": f"£{material.price}",
                    "details": {
                        "category": material.category,
                        "thickness": material.thickness,
                        "slab_size": material.slab_size,
                        "finish": material.finish,
                    },
                    "includes": SERVICES
                }

        return {
            "message": "I couldn't find that material."
        }

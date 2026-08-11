"""MaterialService — the database-backed material catalogue (Sprint 005).

Data-access only, no router: nothing serializes a Material over HTTP this
sprint (confirmed scope decision — materials stay internal, consumed by
quotes/calculator.py and the sales/search assistants, not exposed as
/api/v1/materials). Route-level pattern (get_db(), no repository interface)
per ADR-019, same as app/customers/ and app/auth/.
"""

from sqlalchemy.orm import Session

from app.database import crud
from app.database.models import Material


class MaterialService:
    def list_all(self, db: Session) -> list[Material]:
        return crud.list_materials(db)

    def get_by_name_and_thickness(self, db: Session, name: str, thickness: str) -> Material | None:
        return crud.get_material_by_name_and_thickness(db, name, thickness)


material_service = MaterialService()

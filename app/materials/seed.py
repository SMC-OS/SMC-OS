"""Seeds the material catalogue (Sprint 005) if `materials` is empty.

Guarded exactly like app/activity/seed.py / app/auth/seed.py — only runs
once, against a genuinely empty table, so restarts never duplicate rows.

Pricing/slab-size note (see docs/SPRINTS/sprint-005.md): this is an
illustrative reference catalogue for the quote engine — not sourced from a
live supplier feed, because no such data source exists in this project. An
operator should edit these figures to match real supplier costs before
relying on them commercially. Every material is seeded in both 20mm and
30mm, the 30mm price derived from a single documented markup rather than
picked by hand, so the catalogue stays internally consistent.
"""

import uuid

from app.database import crud
from app.database.database import SessionLocal

THICKNESS_30MM_MARKUP = 1.35
STANDARD_SLAB_SIZE = "3200x1600"

# (name, category, finish, price at 20mm). 30mm price = 20mm price *
# THICKNESS_30MM_MARKUP, rounded to the nearest £10.
_BASE_MATERIALS = [
    # Quartz — the original 3-entry catalogue, prices unchanged, plus 2 more.
    ("Calacatta Gold", "Quartz", "Polished", 2650),
    ("Calacatta Oro", "Quartz", "Polished", 2350),
    ("Nero Marquina", "Quartz", "Polished", 2920),
    ("Statuario White", "Quartz", "Polished", 2500),
    ("Carrara Mist", "Quartz", "Polished", 2450),
    # Granite
    ("Absolute Black", "Granite", "Polished", 3100),
    ("Kashmir White", "Granite", "Polished", 2900),
    ("Baltic Brown", "Granite", "Leathered", 2850),
    # Marble
    ("Carrara White", "Marble", "Polished", 3400),
    ("Emperador Brown", "Marble", "Polished", 3250),
    ("Statuario Marble", "Marble", "Honed", 3600),
    # Porcelain
    ("Grey Concrete Porcelain", "Porcelain", "Matte", 2200),
    ("Calacatta Porcelain", "Porcelain", "Polished", 2400),
    # Dekton
    ("Dekton Sirocco", "Dekton", "Matte", 3300),
    ("Dekton Kelya", "Dekton", "Polished", 3150),
]


def seed_materials() -> None:
    db = SessionLocal()
    try:
        if crud.count_materials(db) > 0:
            return  # already seeded
        for name, category, finish, price_20mm in _BASE_MATERIALS:
            crud.create_material(
                db,
                id=uuid.uuid4(),
                name=name,
                category=category,
                thickness="20mm",
                slab_size=STANDARD_SLAB_SIZE,
                finish=finish,
                price=float(price_20mm),
            )
            crud.create_material(
                db,
                id=uuid.uuid4(),
                name=name,
                category=category,
                thickness="30mm",
                slab_size=STANDARD_SLAB_SIZE,
                finish=finish,
                price=float(round(price_20mm * THICKNESS_30MM_MARKUP / 10) * 10),
            )
    finally:
        db.close()

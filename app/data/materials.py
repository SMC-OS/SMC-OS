# Superseded by the database-backed catalogue (app/materials/seed.py,
# Sprint 005) — no longer imported anywhere. Kept in place rather than
# deleted, per ADR-008 ("archive, don't delete without separate approval");
# there's no backend equivalent of apps/web/_legacy/ to move it to.
MATERIALS = {
    "calacatta gold": {
        "category": "Quartz",
        "thickness": ["20mm", "30mm"],
        "slab_size": "3200x1600",
        "finish": "Polished"
    },

    "calacatta oro": {
        "category": "Quartz",
        "thickness": ["20mm"],
        "slab_size": "3200x1600",
        "finish": "Polished"
    },

    "nero marquina": {
        "category": "Quartz",
        "thickness": ["20mm"],
        "slab_size": "3200x1600",
        "finish": "Polished"
    }
}
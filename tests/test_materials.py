from app.materials.service import material_service


def test_catalogue_covers_all_roadmap_categories(db):
    materials = material_service.list_all(db)
    categories = {m.category for m in materials}
    assert {"Quartz", "Granite", "Marble", "Porcelain", "Dekton"} <= categories


def test_get_by_name_and_thickness_known(db):
    material = material_service.get_by_name_and_thickness(db, "Calacatta Gold", "20mm")
    assert material is not None
    assert material.price == 2650


def test_get_by_name_and_thickness_is_case_insensitive(db):
    material = material_service.get_by_name_and_thickness(db, "CALACATTA GOLD", "20MM")
    assert material is not None


def test_get_by_name_and_thickness_unknown_returns_none(db):
    assert material_service.get_by_name_and_thickness(db, "Not A Material", "20mm") is None


def test_thickness_variants_priced_differently(db):
    thin = material_service.get_by_name_and_thickness(db, "Calacatta Gold", "20mm")
    thick = material_service.get_by_name_and_thickness(db, "Calacatta Gold", "30mm")
    assert thick.price > thin.price

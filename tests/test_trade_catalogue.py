"""GeoCore Premium OS Plan 01, Task 1 — the expanded specialist trade
library. Existing keys/labels must stay stable; this only adds new ones
and proves the additions don't disturb what's already there."""

from app.trades.catalogue import TRADE_KEYS, default_quote_kind, get, label_for

NEW_KEYS = {
    "heating_hvac",
    "tiling",
    "plastering_rendering",
    "brickwork_masonry",
    "groundworks",
    "drainage",
    "windows_doors",
    "glazing",
    "landscaping",
    "fencing",
    "demolition_stripout",
    "insulation",
    "steelwork",
    "scaffolding",
    "solar_renewables",
}

EXISTING_KEYS = {
    "general_building",
    "renovation",
    "extension",
    "kitchen",
    "bathroom",
    "roofing",
    "flooring",
    "decorating",
    "plumbing",
    "electrical",
    "carpentry",
    "stone",
    "other",
}


def test_premium_trade_library_has_stable_new_keys():
    assert NEW_KEYS <= TRADE_KEYS


def test_existing_persisted_keys_remain_unchanged():
    assert EXISTING_KEYS <= TRADE_KEYS
    assert label_for("electrical") == "Electrical"
    assert label_for("plumbing") == "Plumbing"
    assert label_for("carpentry") == "Carpentry & Joinery"
    assert label_for("stone") == "Stone & Worktops"
    assert label_for("other") == "Other"


def test_new_trade_labels_are_correct():
    assert label_for("heating_hvac") == "Heating / HVAC"
    assert label_for("tiling") == "Tiling"
    assert label_for("plastering_rendering") == "Plastering & Rendering"
    assert label_for("brickwork_masonry") == "Brickwork & Masonry"
    assert label_for("groundworks") == "Groundworks"
    assert label_for("drainage") == "Drainage"
    assert label_for("windows_doors") == "Windows & Doors"
    assert label_for("glazing") == "Glazing"
    assert label_for("landscaping") == "Landscaping"
    assert label_for("fencing") == "Fencing"
    assert label_for("demolition_stripout") == "Demolition / Strip-Out"
    assert label_for("insulation") == "Insulation"
    assert label_for("steelwork") == "Structural Steelwork"
    assert label_for("scaffolding") == "Scaffolding"
    assert label_for("solar_renewables") == "Solar & Renewables"


def test_quote_kind_defaults_unchanged():
    assert default_quote_kind("stone") == "stone"
    assert default_quote_kind("electrical") == "general"
    assert default_quote_kind("heating_hvac") == "general"
    assert default_quote_kind(None) == "general"
    assert default_quote_kind("not-a-real-trade") == "general"


def test_new_trades_are_gettable():
    for key in NEW_KEYS:
        trade = get(key)
        assert trade is not None
        assert trade.key == key

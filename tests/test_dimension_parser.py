from app.quotes.dimension_parser import parse_dimension_text


def test_parses_bare_mm_pair():
    d = parse_dimension_text("2400 x 600")
    assert d.length_mm == 2400
    assert d.width_mm == 600
    assert d.unit_input == "mm"


def test_parses_explicit_mm_pair():
    d = parse_dimension_text("2400mm x 600mm")
    assert d.length_mm == 2400
    assert d.width_mm == 600


def test_parses_metres_by_mm_mixed_units():
    d = parse_dimension_text("2.4m by 600mm")
    assert d.length_mm == 2400
    assert d.width_mm == 600
    assert d.unit_input == "m"


def test_parses_length_width_thickness_triple():
    d = parse_dimension_text("island 2200 x 1000 x 20mm")
    assert d.length_mm == 2200
    assert d.width_mm == 1000
    assert d.thickness_mm == 20


def test_parses_digit_quantity_with_pieces():
    d = parse_dimension_text("2 pieces 1200 x 600")
    assert d.quantity == 2
    assert d.length_mm == 1200
    assert d.width_mm == 600


def test_parses_word_quantity_with_pieces():
    d = parse_dimension_text("two pieces 1200 x 600")
    assert d.quantity == 2


def test_parses_standalone_metre_length_no_pair():
    d = parse_dimension_text("3.5m kitchen run")
    assert d.length_mm == 3500
    assert d.width_mm is None
    assert d.unit_input == "m"


def test_bare_mm_thickness_alone_is_not_mistaken_for_length():
    d = parse_dimension_text("20mm Calacatta Oro")
    assert d.thickness_mm == 20
    assert d.length_mm is None


def test_no_dimensions_at_all_returns_all_none():
    d = parse_dimension_text("please quote something for me")
    assert d.length_mm is None
    assert d.width_mm is None
    assert d.thickness_mm is None
    assert d.quantity is None


def test_centimetres_are_converted_correctly():
    d = parse_dimension_text("240cm x 60cm")
    assert d.length_mm == 2400
    assert d.width_mm == 600

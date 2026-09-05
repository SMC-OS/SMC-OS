"""Units a general construction quote line can be priced in (Sprint 036).

A curated list, not free text: a unit is a label rendered next to a
quantity on a customer-facing document, and letting every user invent
their own produces "sqm", "sq m", "m2", "m²" and "SQM" on four quotes from
the same company. Nothing arithmetic is ever done with a unit — quantity x
unit_price is unit-agnostic — so this list is about consistency of
presentation, not about conversion.

`item` is first because it is the honest default for a line someone has
not thought about yet ("Bi-fold doors, 1 item").
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Unit:
    key: str
    label: str


UNITS: tuple[Unit, ...] = (
    Unit("item", "item"),
    Unit("job", "job"),
    Unit("hour", "hour"),
    Unit("day", "day"),
    Unit("week", "week"),
    Unit("m", "linear metre"),
    Unit("m2", "square metre"),
    Unit("m3", "cubic metre"),
    Unit("tonne", "tonne"),
    Unit("pack", "pack"),
    Unit("visit", "visit"),
)

UNIT_KEYS: frozenset[str] = frozenset(unit.key for unit in UNITS)

_BY_KEY = {unit.key: unit for unit in UNITS}


def label_for(key: str | None) -> str | None:
    unit = _BY_KEY.get(key) if key else None
    return unit.label if unit else None

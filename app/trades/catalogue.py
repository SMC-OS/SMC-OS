"""The trades GeoCore supports — the single vocabulary shared by quotes,
projects and onboarding (Sprint 036).

Before this sprint GeoCore had no notion of "what kind of work is this",
because every job was a stone job. That assumption was baked into the
quote schema, the project pipeline, the AI prompt, the onboarding copy and
the dashboard. This module is the one place that answers it now, and every
consumer reads from here rather than keeping its own near-identical list:

  * `quotes.trade` — what a quote is for.
  * `projects.project_type` — what a job is. Same keys, so an approved
    quote hands its trade straight to the project it becomes rather than
    mapping between two lists that will drift.
  * `tenants.trades` — what a business does, chosen during onboarding, used
    to pre-select a quote template and recommend automations.

Keys are stable identifiers persisted in the database and must not change
once shipped; labels are display text and may be reworded freely. "stone"
is one entry among twelve — deliberately not first, and deliberately not
special — because that is the entire point of this sprint.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Trade:
    key: str
    label: str
    # Which quote template this trade opens by default. "stone" is the
    # only trade with a specialist template today (the slab calculator);
    # everything else uses the general line-item quote. This is a
    # per-trade default the user can always override, never a restriction.
    default_quote_kind: str = "general"


TRADES: tuple[Trade, ...] = (
    Trade("general_building", "General Building"),
    Trade("renovation", "Renovation"),
    Trade("extension", "Extensions"),
    Trade("kitchen", "Kitchens"),
    Trade("bathroom", "Bathrooms"),
    Trade("roofing", "Roofing"),
    Trade("flooring", "Flooring"),
    Trade("decorating", "Decorating"),
    Trade("plumbing", "Plumbing"),
    Trade("electrical", "Electrical"),
    Trade("carpentry", "Carpentry & Joinery"),
    Trade("stone", "Stone & Worktops", default_quote_kind="stone"),
    Trade("other", "Other"),
)

TRADE_KEYS: frozenset[str] = frozenset(trade.key for trade in TRADES)

_BY_KEY = {trade.key: trade for trade in TRADES}


def get(key: str | None) -> Trade | None:
    return _BY_KEY.get(key) if key else None


def label_for(key: str | None) -> str | None:
    trade = get(key)
    return trade.label if trade else None


def default_quote_kind(key: str | None) -> str:
    """Which quote template a trade opens by default. An unknown or absent
    trade gets the general quote — the general case is the default, and a
    caller that names no trade is never assumed to be quoting stone."""
    trade = get(key)
    return trade.default_quote_kind if trade else "general"


def parse_selection(raw: str | None) -> list[str]:
    """Read `tenants.trades` (a comma-separated key list) back into keys,
    dropping anything not in the catalogue. Unknown keys are silently
    ignored rather than raising: a trade removed from the catalogue in a
    future release must not make an existing workspace unloadable."""
    if not raw:
        return []
    return [key for key in (part.strip() for part in raw.split(",")) if key in TRADE_KEYS]


def serialize_selection(keys: list[str]) -> str:
    """Write a key list back to `tenants.trades`, de-duplicated and in
    catalogue order so the stored value is stable regardless of the order
    the user happened to click them in."""
    chosen = {key for key in keys if key in TRADE_KEYS}
    return ",".join(trade.key for trade in TRADES if trade.key in chosen)

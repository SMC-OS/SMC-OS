"""Universal (general construction) quoting — Sprint 036, Workstream E.

GeoCore is an operating system for construction and renovation businesses.
Until this sprint its only quote was a stone quote: priced by slab area,
requiring a material, a thickness and a run length, and structurally
incapable of expressing "Strip out existing bathroom — 2 days labour @
£320/day" or "Scaffold hire — 1 job @ £1,450".

This module is the general case. It does NOT replace the stone path: the
slab calculator (app/quotes/calculator.py), the dimension parser, the
material catalogue and the AI draft extractor are all untouched and remain
the specialist workflow for stone, marble, quartz, granite and worktops.
A quote now simply declares which kind it is.

Pricing here is deliberately trivial and fully deterministic —
quantity x unit_price, summed, discounted, taxed. There is no clever
estimating and no AI in this path. The person quoting a roof knows what a
roof costs; GeoCore's job is to arrange, total and present that
correctly, not to invent it. (Compare ADR-024: the AI layer is barred
from producing a monetary figure by the shape of its schema, not by
instruction.)

Rounding rule, applied once and stated here so no caller re-derives it:
each line is rounded to 2dp, then the lines are summed. Summing unrounded
floats and rounding at the end produces totals that disagree with the
line items a customer can add up themselves on the PDF, which is the one
arithmetic error a quote must never make.
"""

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.trades.catalogue import TRADE_KEYS
from app.trades.units import UNIT_KEYS

# What a general line represents. "stone" is absent on purpose: a stone
# line is created only by the slab calculator, never by this request
# model, so a client cannot hand-craft a slab line with a made-up price
# and bypass the material catalogue entirely.
LINE_KINDS = {"labour", "material", "other"}

# A quote with no lines has no price, and a quote with hundreds is a
# schedule of works, not a quote — the cap exists so one request cannot
# create unbounded rows.
MAX_LINES = 200


class GeneralQuoteLineRequest(BaseModel):
    line_kind: str = "labour"
    description: str = Field(min_length=1, max_length=500)
    quantity: float = 1.0
    unit: str = "item"
    unit_price: float = 0.0
    notes: str | None = None

    @field_validator("line_kind")
    @classmethod
    def _known_line_kind(cls, value: str) -> str:
        if value not in LINE_KINDS:
            raise ValueError(f"line_kind must be one of {sorted(LINE_KINDS)}")
        return value

    @field_validator("unit")
    @classmethod
    def _known_unit(cls, value: str) -> str:
        if value not in UNIT_KEYS:
            raise ValueError(f"unit must be one of {sorted(UNIT_KEYS)}")
        return value

    @field_validator("quantity", "unit_price")
    @classmethod
    def _not_negative(cls, value: float) -> float:
        # Zero is allowed on both: a £0 line is a legitimate way to show an
        # included-at-no-charge item on a quote. Negative is not — a
        # negative line is a discount, and discounts have their own field
        # so they appear as a discount on the document rather than hiding
        # inside the line items.
        if value < 0:
            raise ValueError("must not be negative")
        return value


class GeneralQuoteRequest(BaseModel):
    """The create body for a general construction quote.

    `title` is required and `lines` must be non-empty: those two are what
    make this a quote rather than an empty draft, and accepting either as
    blank would produce documents that cannot be sent to anyone.

    `customer_id` is optional so a quote can be priced before the customer
    record exists (the same allowance ADR-023 makes for the public stone
    endpoint). When it is set, the service validates it belongs to the
    caller's own tenant before writing anything.
    """

    customer_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=200)
    trade: str | None = None

    site_address_line1: str | None = None
    site_address_line2: str | None = None
    site_city: str | None = None
    site_postcode: str | None = None

    scope_of_works: str | None = None
    notes: str | None = None
    exclusions: str | None = None
    terms: str | None = None
    valid_until: date | None = None

    vat_rate: float = 0.20
    discount_amount: float | None = None

    lines: list[GeneralQuoteLineRequest] = Field(min_length=1, max_length=MAX_LINES)

    @field_validator("trade")
    @classmethod
    def _known_trade(cls, value: str | None) -> str | None:
        if value is not None and value not in TRADE_KEYS:
            raise ValueError(f"trade must be one of {sorted(TRADE_KEYS)}")
        return value

    @field_validator("vat_rate")
    @classmethod
    def _sane_vat_rate(cls, value: float) -> float:
        # A rate, not a percentage: 0.20, never 20. The upper bound is
        # generous rather than UK-specific (the schema is not allowed to
        # assume one jurisdiction forever) but still rules out the
        # commonest data-entry error, entering 20 and taxing a quote
        # 2000%.
        if not 0 <= value <= 1:
            raise ValueError("vat_rate must be a rate between 0 and 1 (e.g. 0.2 for 20%)")
        return value

    @field_validator("discount_amount")
    @classmethod
    def _not_negative_discount(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("discount_amount must not be negative")
        return value


class GeneralQuoteUpdate(BaseModel):
    """Partial update of a general quote's envelope, plus optional
    wholesale replacement of its lines.

    `lines` is replace-all rather than a per-line patch: a quote's line
    items are edited as a set in the UI (rows added, reordered, deleted),
    and a per-line diff protocol would add identity and ordering
    complexity for no user-visible gain. Omitting `lines` leaves the
    existing ones completely untouched.

    Only a draft may be updated — see QuoteService.update_general. A quote
    that has been sent to a customer or approved is a document someone
    else is holding; silently changing its prices underneath them is not
    an edit, it is a substitution.
    """

    customer_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    trade: str | None = None
    site_address_line1: str | None = None
    site_address_line2: str | None = None
    site_city: str | None = None
    site_postcode: str | None = None
    scope_of_works: str | None = None
    notes: str | None = None
    exclusions: str | None = None
    terms: str | None = None
    valid_until: date | None = None
    vat_rate: float | None = None
    discount_amount: float | None = None
    lines: list[GeneralQuoteLineRequest] | None = Field(default=None, max_length=MAX_LINES)

    @field_validator("trade")
    @classmethod
    def _known_trade(cls, value: str | None) -> str | None:
        if value is not None and value not in TRADE_KEYS:
            raise ValueError(f"trade must be one of {sorted(TRADE_KEYS)}")
        return value

    @field_validator("vat_rate")
    @classmethod
    def _sane_vat_rate(cls, value: float | None) -> float | None:
        if value is not None and not 0 <= value <= 1:
            raise ValueError("vat_rate must be a rate between 0 and 1 (e.g. 0.2 for 20%)")
        return value

    @field_validator("lines")
    @classmethod
    def _at_least_one_line(
        cls, value: list[GeneralQuoteLineRequest] | None
    ) -> list[GeneralQuoteLineRequest] | None:
        # `lines: null`/omitted means "don't touch the lines"; `lines: []`
        # would mean "this quote now prices nothing", which is not a state
        # a quote is allowed to reach.
        if value is not None and not value:
            raise ValueError("lines must contain at least one line item")
        return value


class GeneralQuoteTotals(BaseModel):
    model_config = ConfigDict(frozen=True)

    subtotal: float
    discount_amount: float
    price_before_vat: float
    vat: float
    total: float
    line_totals: list[float]


def price(
    lines: list[GeneralQuoteLineRequest],
    *,
    vat_rate: float,
    discount_amount: float | None,
) -> GeneralQuoteTotals:
    """The whole of general-quote pricing.

    Deliberately a pure function taking no Session: unlike the stone
    calculator it needs no material catalogue lookup, so it can be unit
    tested exhaustively with no database at all.

    A discount larger than the subtotal is clamped to the subtotal rather
    than rejected. Someone entering "£5,000 off" on a £4,800 job means
    "make it free", and the correct outcome is a zero quote, never a
    negative one that would render as a credit note on the PDF and as
    negative quoted value on the dashboard.
    """
    line_totals = [round(line.quantity * line.unit_price, 2) for line in lines]
    subtotal = round(sum(line_totals), 2)

    discount = min(round(discount_amount or 0.0, 2), subtotal)
    price_before_vat = round(subtotal - discount, 2)
    vat = round(price_before_vat * vat_rate, 2)

    return GeneralQuoteTotals(
        subtotal=subtotal,
        discount_amount=discount,
        price_before_vat=price_before_vat,
        vat=vat,
        total=round(price_before_vat + vat, 2),
        line_totals=line_totals,
    )

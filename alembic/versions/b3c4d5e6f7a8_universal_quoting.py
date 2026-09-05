"""universal quoting (general construction quotes alongside stone)

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7

Sprint 036, Workstream E — the central schema change of this sprint.

THE PROBLEM

`quotes` was not a quote table, it was a worktop table. `material`,
`thickness`, `kitchen_length` and `length_mm` were all NOT NULL, so a quote
could not physically be inserted without slab dimensions. `quote_items`
(Sprint 033) was genuinely multi-line but every line was a slab, priced
through the area/slab-area calculator. There was no way to express "Strip
out existing bathroom — 2 days labour @ £320/day", let alone a roofing or
groundworks quote.

THE CHANGE

Two things, in one migration because they are one change:

1. A `quote_kind` discriminator ('stone' | 'general') and a `line_kind`
   discriminator on each item ('stone' | 'labour' | 'material' | 'other').
   Both NOT NULL with a 'stone' server default, which states a fact about
   every existing row rather than guessing one: before this migration, a
   quote could not have been anything else.

2. The general quote envelope — what the job is, where it is, what is
   included and excluded, how long the price holds, what currency it is
   in, what VAT rate applies, and what discount was given. All nullable
   or defaulted.

WHY NOT NULL IS DROPPED (and why that is safe)

`quotes.material`, `quotes.thickness`, `quotes.kitchen_length`,
`quotes.length_mm` and `quote_items.material`, `quote_items.thickness`,
`quote_items.length_mm`, `quote_items.width_mm` become nullable.

A general quote genuinely has no slab material, no thickness and no run
length. The alternative — writing a sentinel like 'N/A' or 0 into a NOT
NULL column — would put a lie in the data to avoid changing the schema,
and every reader would then have to know which sentinel meant "absent".

Dropping NOT NULL is a pure widening: every existing row keeps every value
it has, no row is rewritten, no existing query can start failing (a
predicate that was true stays true), and no existing INSERT becomes
invalid. Postgres performs it as a catalogue-only change with no table
rewrite and no long lock.

WHY quantity IS WIDENED

`quote_items.quantity` goes INTEGER -> DOUBLE PRECISION. A stone line is 2
slabs; a labour line is 2.5 days. Postgres widens int -> float8 in place
with an implicit, lossless cast. The JSON a client sees changes from `1`
to `1.0`, which is the same number to Python's `==` and to JavaScript's
`===` and `String()` — verified against the existing assertions in
tests/test_quote_items.py and apps/web before making this change.

WHY THE DOWNGRADE REFUSES

Reversing this cannot silently succeed once a general quote exists: the
NOT NULL constraints cannot be restored while rows legitimately hold NULL
there, and deleting a tenant's real quotes to make a schema fit is
destruction disguised as a migration. `downgrade()` therefore raises if
any general quote or non-stone line exists, and tells the operator exactly
what to decide. It downgrades cleanly on a database that only ever held
stone quotes, which is the only case where reversal is genuinely lossless.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column) pairs whose NOT NULL is dropped. Kept as data so
# upgrade() and downgrade() cannot drift apart.
_RELAXED: tuple[tuple[str, str, sa.types.TypeEngine], ...] = (
    ("quotes", "material", sa.String()),
    ("quotes", "thickness", sa.String()),
    ("quotes", "kitchen_length", sa.Float()),
    ("quotes", "length_mm", sa.Float()),
    ("quote_items", "material", sa.String()),
    ("quote_items", "thickness", sa.String()),
    ("quote_items", "length_mm", sa.Float()),
    ("quote_items", "width_mm", sa.Float()),
)

_QUOTE_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("title", sa.String()),
    ("trade", sa.String()),
    ("site_address_line1", sa.String()),
    ("site_address_line2", sa.String()),
    ("site_city", sa.String()),
    ("site_postcode", sa.String()),
    ("scope_of_works", sa.Text()),
    ("notes", sa.Text()),
    ("exclusions", sa.Text()),
    ("terms", sa.Text()),
    ("valid_until", sa.Date()),
    ("subtotal", sa.Float()),
    ("discount_amount", sa.Float()),
    ("sent_at", sa.DateTime(timezone=True)),
)

_ITEM_COLUMNS: tuple[tuple[str, sa.types.TypeEngine], ...] = (
    ("description", sa.String()),
    ("unit", sa.String()),
    ("unit_price", sa.Float()),
)


def upgrade() -> None:
    op.add_column(
        "quotes",
        sa.Column("quote_kind", sa.String(), nullable=False, server_default="stone"),
    )
    op.add_column(
        "quotes",
        sa.Column("currency", sa.String(), nullable=False, server_default="GBP"),
    )
    op.add_column(
        "quotes",
        sa.Column("vat_rate", sa.Float(), nullable=False, server_default="0.2"),
    )
    for name, column_type in _QUOTE_COLUMNS:
        op.add_column("quotes", sa.Column(name, column_type, nullable=True))

    op.add_column(
        "quote_items",
        sa.Column("line_kind", sa.String(), nullable=False, server_default="stone"),
    )
    for name, column_type in _ITEM_COLUMNS:
        op.add_column("quote_items", sa.Column(name, column_type, nullable=True))

    for table, column, column_type in _RELAXED:
        op.alter_column(table, column, existing_type=column_type, nullable=True)

    # INTEGER -> DOUBLE PRECISION. postgresql_using is explicit rather than
    # relying on the implicit cast, so the intent is readable in the DDL
    # this emits.
    op.alter_column(
        "quote_items",
        "quantity",
        existing_type=sa.Integer(),
        type_=sa.Float(),
        existing_nullable=False,
        existing_server_default="1",
        postgresql_using="quantity::double precision",
    )


def downgrade() -> None:
    bind = op.get_bind()

    general_quotes = bind.execute(
        sa.text("SELECT count(*) FROM quotes WHERE quote_kind <> 'stone'")
    ).scalar_one()
    general_items = bind.execute(
        sa.text("SELECT count(*) FROM quote_items WHERE line_kind <> 'stone'")
    ).scalar_one()

    if general_quotes or general_items:
        raise RuntimeError(
            "Refusing to downgrade b3c4d5e6f7a8: this database holds "
            f"{general_quotes} general quote(s) and {general_items} non-stone "
            "line item(s). Reversing this migration would require deleting "
            "them or writing fabricated slab dimensions into them. Decide "
            "explicitly which of those you want, do it as its own reviewed "
            "step, then re-run the downgrade."
        )

    op.alter_column(
        "quote_items",
        "quantity",
        existing_type=sa.Float(),
        type_=sa.Integer(),
        existing_nullable=False,
        existing_server_default="1",
        postgresql_using="round(quantity)::integer",
    )

    for table, column, column_type in reversed(_RELAXED):
        op.alter_column(table, column, existing_type=column_type, nullable=False)

    for name, _ in reversed(_ITEM_COLUMNS):
        op.drop_column("quote_items", name)
    op.drop_column("quote_items", "line_kind")

    for name, _ in reversed(_QUOTE_COLUMNS):
        op.drop_column("quotes", name)
    op.drop_column("quotes", "vat_rate")
    op.drop_column("quotes", "currency")
    op.drop_column("quotes", "quote_kind")

"""expand customer profile (construction customer record)

Revision ID: f1a2b3c4d5e6
Revises: e2c7b41d9a53

Sprint 036, Workstream D. Until now a GeoCore customer was three columns:
name, email, phone. That is a contact, not a customer record for a
construction or renovation business — there was nowhere to put the site
town, the postcode a job is priced against, whether the customer is a
homeowner or a main contractor, or a single note about them.

Every column added here is nullable or carries a server default, so:

  * no existing customer row needs a backfill and none is rewritten;
  * the existing POST /api/v1/customers body ({name, email, phone}) keeps
    working byte-for-byte, which matters because it is the body the
    enquiry-conversion path (Sprint 021) and the E2E suite both send.

`customer_type` is NOT NULL with server_default 'individual'. That is a
statement of fact about existing rows rather than a guess: no customer
created before this sprint carried a company name, because there was no
column to carry one in.

`notes` is Text rather than String — it is the one free-form field here
that a user will genuinely paste paragraphs into. Everything else is a
single line.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e2c7b41d9a53"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column(
            "customer_type",
            sa.String(),
            nullable=False,
            server_default="individual",
        ),
    )
    op.add_column("customers", sa.Column("company_name", sa.String(), nullable=True))
    op.add_column("customers", sa.Column("address_line1", sa.String(), nullable=True))
    op.add_column("customers", sa.Column("address_line2", sa.String(), nullable=True))
    op.add_column("customers", sa.Column("city", sa.String(), nullable=True))
    op.add_column("customers", sa.Column("postcode", sa.String(), nullable=True))
    op.add_column("customers", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("customers", "notes")
    op.drop_column("customers", "postcode")
    op.drop_column("customers", "city")
    op.drop_column("customers", "address_line2")
    op.drop_column("customers", "address_line1")
    op.drop_column("customers", "company_name")
    op.drop_column("customers", "customer_type")

"""Record the Stripe time of the last event applied to a subscription so an older, late-delivered event can never
undo a newer one (Stripe does not guarantee delivery order). Additive: nullable column, existing rows unchanged."""
from alembic import op
import sqlalchemy as sa

revision = "c7d8e9f0a1b2"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("subscriptions", sa.Column("stripe_event_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("subscriptions", "stripe_event_at")

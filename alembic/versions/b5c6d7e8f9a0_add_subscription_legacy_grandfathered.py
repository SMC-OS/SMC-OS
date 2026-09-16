"""add subscription legacy_grandfathered flag

Revision ID: b5c6d7e8f9a0
Revises: a3b4c5d6e7f8

Sprint 039 Production Readiness Defect Gate, final auth + trial gate
(GEOCORE V1 — FINAL AUTH + TRIAL ACCESS GATES).

THE CHANGE: the owner's V1 trial contract now requires a payment card
before a verified account can reach the normal GeoCore workspace (see
app/auth/dependencies.py's require_billing_access) — workspace APIs
require an authoritative server-side Subscription with status
"trialing" or "active", both of which now only ever come from a real
Stripe Checkout completing.

THE EXPLICIT GRACE POLICY this migration implements (owner's own
requirement — "do not accidentally lock legitimate existing GeoCore
production users out"; "existing tenants require an explicit
migration/grace policy rather than accidental behaviour"): every
Subscription row that exists AT THE TIME THIS MIGRATION RUNS —
including the old card-less 14-day trials app/billing/trial.py has
been creating since Sprint 039 Blocker 3, and any already-paying
Stripe subscription — predates the new card-required contract and is
permanently exempt from it, recorded here as a real, one-time data
migration rather than re-derived at request time from a timestamp
comparison (which a re-seeded/test database can't reproduce
faithfully — see the new `legacy_grandfathered` column's use in
app/auth/dependencies.py::has_active_billing_access). Any tenant with
no Subscription row at all as of this migration (should be rare —
every signup since Blocker 3 has created one — but not provably
impossible) also gets one inserted here, exempt the same way, so no
pre-existing tenant is locked out purely for lacking a row.

New tenants created after this migration (via the public signup
endpoint) get NO Subscription row at all until a real Stripe Checkout
completes — `legacy_grandfathered` defaults to false for any row
created from this point on, whether by a genuine Checkout webhook or
by app/auth/service.py::AuthService.create_user()'s own
grant_legacy_billing_access convenience default (test fixtures, the
dev seed script, and invitation-accept — every one of those callers
represents an already-established tenant, not the public self-signup
flow, exactly the same reasoning already established for
email_verified on that same method).
"""

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "subscriptions",
        sa.Column(
            "legacy_grandfathered", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )

    # Every subscription that already exists as of this migration predates
    # the card-required contract — grandfather it permanently.
    op.execute("UPDATE subscriptions SET legacy_grandfathered = true")

    # Any tenant with no subscription row at all yet (pre-billing-feature
    # legacy, or any other edge case) gets a safe, unmetered placeholder —
    # same "active, no Stripe object" shape trial.py already used for the
    # old no-card trial, just permanently exempt rather than time-limited.
    connection = op.get_bind()
    orphan_tenant_ids = connection.execute(
        sa.text(
            "SELECT t.id FROM tenants t "
            "LEFT JOIN subscriptions s ON s.tenant_id = t.id "
            "WHERE s.id IS NULL"
        )
    ).fetchall()
    for (tenant_id,) in orphan_tenant_ids:
        connection.execute(
            sa.text(
                "INSERT INTO subscriptions "
                "(id, tenant_id, plan, billing_period, status, cancel_at_period_end, "
                " legacy_grandfathered) "
                "VALUES (:id, :tenant_id, 'pro', 'monthly', 'active', false, true)"
            ),
            {"id": str(uuid.uuid4()), "tenant_id": str(tenant_id)},
        )


def downgrade() -> None:
    op.drop_column("subscriptions", "legacy_grandfathered")

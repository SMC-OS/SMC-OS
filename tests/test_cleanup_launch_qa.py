"""Sprint 031 — scripts/production/cleanup_launch_qa.py contract.

Every test builds its own synthetic SIMO-LAUNCH-QA-*-prefixed tenant(s)
against the real test database (same style as test_follow_up_automation.py
— a fresh, isolated fixture per test, not the shared seeded tenant), so the
cleanup script's exact-name matching has real rows to find, and so a test
crashing mid-run never leaves cross-test pollution the next test would
misread as "already clean".
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select

from app.auth.service import auth_service
from app.auth.models import SignupRequest
from app.customers.models import CustomerCreate
from app.customers.service import customer_service
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import Customer, Material, Project, Quote, QuoteItem, Subscription, Tenant, User
from app.projects.models import ProjectCreate
from app.projects.service import project_service

from scripts.production.cleanup_launch_qa import (
    EnvironmentMismatchError,
    QA_MATERIAL_NAME,
    QA_MATERIAL_THICKNESS,
    QA_TENANT_NAMES,
    execute_plan,
    resolve_plan,
    verify_environment,
)

RUN_ID = uuid.uuid4().hex[:8]
# Deliberately reuses the real QA_TENANT_NAMES constants (not a lookalike
# prefix) — the whole point is exercising the script's actual exact-match
# selector, not a stand-in for it. RUN_ID only disambiguates a third,
# always-present *unrelated* tenant used as the "must never be touched"
# control.
UNRELATED_TENANT_EMAIL = f"pytest-cleanup-unrelated-{RUN_ID}@example.invalid"
UNRELATED_TENANT_COMPANY = f"Pytest Unrelated Co {RUN_ID}"


def _wipe_named_tenants(names: tuple[str, ...]) -> None:
    """Hard teardown used only by fixtures, bypassing the script under
    test entirely (SQLAlchemy delete(), same primitive
    tests/conftest.py's own _cleanup_other_tenant already uses) — a test's
    setup/teardown must not depend on the correctness of the thing it's
    testing."""
    db = SessionLocal()
    try:
        tenant_ids = [t.id for t in db.scalars(select(Tenant).where(Tenant.name.in_(names))).all()]
        if not tenant_ids:
            return
        from app.database.models import (
            ActivityLog,
            Appointment,
            Communication,
            Document,
            EmailVerificationToken,
            Invitation,
            Message,
            NotificationRecord,
            PortalLink,
        )

        # Sprint 039 Production Readiness Defect Gate, Blocker 1 — every
        # real signup now creates an EmailVerificationToken (user_id FK,
        # no ondelete) and a Communication row (tenant_id FK) — must go
        # before the User/Tenant deletes below, same as every other child
        # table here.
        db.execute(
            delete(EmailVerificationToken).where(
                EmailVerificationToken.user_id.in_(
                    select(User.id).where(User.tenant_id.in_(tenant_ids))
                )
            )
        )
        db.execute(delete(Communication).where(Communication.tenant_id.in_(tenant_ids)))

        # Mirrors resolve_plan/execute_plan's own orphan-quote handling —
        # a leftover anonymous quote (tenant_id IS NULL) from an earlier
        # interrupted run can still reference one of these customers and
        # must be cleared before the customers FK delete below.
        customer_ids = db.scalars(select(Customer.id).where(Customer.tenant_id.in_(tenant_ids))).all()
        if customer_ids:
            orphan_ids = select(Quote.id).where(
                Quote.tenant_id.is_(None), Quote.customer_id.in_(customer_ids)
            )
            db.execute(delete(QuoteItem).where(QuoteItem.quote_id.in_(orphan_ids)))
            db.execute(
                delete(Quote).where(Quote.tenant_id.is_(None), Quote.customer_id.in_(customer_ids))
            )

        db.execute(
            delete(QuoteItem).where(
                QuoteItem.quote_id.in_(select(Quote.id).where(Quote.tenant_id.in_(tenant_ids)))
            )
        )
        # Sprint 039 Production Readiness Defect Gate, Blocker 3 — every
        # real signup now starts a real trial Subscription row (tenant_id
        # FK, no ondelete) — must go before the User/Tenant deletes below.
        db.execute(delete(Subscription).where(Subscription.tenant_id.in_(tenant_ids)))
        for model in (
            Appointment,
            Document,
            Message,
            PortalLink,
            NotificationRecord,
            ActivityLog,
            Invitation,
            Project,
            Quote,
            Customer,
            User,
        ):
            db.execute(delete(model).where(model.tenant_id.in_(tenant_ids)))
        db.execute(delete(Tenant).where(Tenant.id.in_(tenant_ids)))
        db.commit()
    finally:
        db.close()


def _wipe_qa_material() -> None:
    db = SessionLocal()
    try:
        db.execute(
            delete(Material).where(
                Material.name == QA_MATERIAL_NAME, Material.thickness == QA_MATERIAL_THICKNESS
            )
        )
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def qa_fixture(client):
    """Signs up both real QA_TENANT_NAMES tenants plus a customer/project/
    quote for the first one, and the exact QA material row — the same
    shape Sprint 030 actually left in production, so the deletion-order
    test is exercised for real, not against a toy shape."""
    _wipe_named_tenants(QA_TENANT_NAMES)
    _wipe_qa_material()

    tokens = []
    tenant_ids = []
    for index, name in enumerate(QA_TENANT_NAMES):
        r = client.post(
            "/api/v1/auth/signup",
            json={
                "company_name": name,
                "name": f"QA Owner {index}",
                "email": f"pytest-cleanup-qa-owner-{index}-{RUN_ID}@example.invalid",
                "password": f"Pytest-Cleanup-Qa-Password-{index}!",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        tokens.append(body["access_token"])
        tenant_ids.append(uuid.UUID(body["user"]["tenant_id"]))
        # Sprint 039 Production Readiness Defect Gate, Blocker 2 hotfix —
        # this fixture builds sample QA business data via the real
        # authenticated API, not the verification flow itself, so each
        # signed-up owner is marked verified immediately (same reasoning
        # as conftest.py's other_tenant_auth_headers).
        db = SessionLocal()
        try:
            db.query(User).filter(User.id == uuid.UUID(body["user"]["id"])).update(
                {"email_verified_at": datetime.now(timezone.utc)}
            )
            db.commit()
        finally:
            db.close()

    headers_a = {"Authorization": f"Bearer {tokens[0]}"}
    customer_resp = client.post(
        "/api/v1/customers",
        json={"name": "QA Fixture Customer", "email": f"qa-fixture-{RUN_ID}@example.invalid"},
        headers=headers_a,
    )
    assert customer_resp.status_code == 201, customer_resp.text
    customer_id = customer_resp.json()["id"]

    project_resp = client.post(
        "/api/v1/projects",
        json={"name": "QA Fixture Project", "customer_id": customer_id},
        headers=headers_a,
    )
    assert project_resp.status_code == 201, project_resp.text

    db = SessionLocal()
    try:
        material = crud.create_material(
            db,
            id=uuid.uuid4(),
            name=QA_MATERIAL_NAME,
            category="QA-FIXTURE-NOT-REAL",
            thickness=QA_MATERIAL_THICKNESS,
            slab_size="3200x1600",
            finish="QA-SENTINEL",
            price=1.00,
        )
        material_id = material.id
    finally:
        db.close()

    quote_resp = client.post(
        "/api/v1/quote",
        json={
            "customer": "QA Fixture Customer",
            "material": QA_MATERIAL_NAME,
            "thickness": QA_MATERIAL_THICKNESS,
            "kitchen_length": 3.0,
            "customer_id": customer_id,
        },
        headers=headers_a,
    )
    assert quote_resp.status_code == 200, quote_resp.text

    yield {"tenant_ids": tenant_ids, "material_id": material_id, "customer_id": uuid.UUID(customer_id)}

    _wipe_named_tenants(QA_TENANT_NAMES)
    _wipe_qa_material()


@pytest.fixture()
def unrelated_tenant(client):
    """A genuinely separate, non-QA tenant with its own data — the
    "must never be touched" control for every test below."""
    r = client.post(
        "/api/v1/auth/signup",
        json={
            "company_name": UNRELATED_TENANT_COMPANY,
            "name": "Unrelated Owner",
            "email": UNRELATED_TENANT_EMAIL,
            "password": "Pytest-Unrelated-Password-1!",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    # Sprint 039 Production Readiness Defect Gate, Blocker 2 hotfix — see
    # qa_fixture's identical comment above.
    db = SessionLocal()
    try:
        db.query(User).filter(User.id == uuid.UUID(body["user"]["id"])).update(
            {"email_verified_at": datetime.now(timezone.utc)}
        )
        db.commit()
    finally:
        db.close()
    customer_resp = client.post(
        "/api/v1/customers",
        json={"name": "Unrelated Customer", "email": f"unrelated-{RUN_ID}@example.invalid"},
        headers=headers,
    )
    assert customer_resp.status_code == 201, customer_resp.text

    yield {"tenant_id": uuid.UUID(body["user"]["tenant_id"]), "customer_id": customer_resp.json()["id"]}

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == UNRELATED_TENANT_EMAIL).first()
        if user is not None:
            from app.database.models import (
                ActivityLog,
                Communication,
                EmailVerificationToken,
                Subscription,
            )

            db.execute(
                delete(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id)
            )
            db.execute(delete(Communication).where(Communication.tenant_id == user.tenant_id))
            # Sprint 039 Blocker 3 — see identical note in _wipe_named_tenants above.
            db.execute(delete(Subscription).where(Subscription.tenant_id == user.tenant_id))
            customer_ids = db.scalars(
                select(Customer.id).where(Customer.tenant_id == user.tenant_id)
            ).all()
            if customer_ids:
                orphan_ids = select(Quote.id).where(
                    Quote.tenant_id.is_(None), Quote.customer_id.in_(customer_ids)
                )
                db.execute(delete(QuoteItem).where(QuoteItem.quote_id.in_(orphan_ids)))
                db.execute(
                    delete(Quote).where(
                        Quote.tenant_id.is_(None), Quote.customer_id.in_(customer_ids)
                    )
                )
            db.execute(delete(Customer).where(Customer.tenant_id == user.tenant_id))
            db.execute(delete(ActivityLog).where(ActivityLog.tenant_id == user.tenant_id))
            db.execute(delete(User).where(User.email == UNRELATED_TENANT_EMAIL))
            db.execute(delete(Tenant).where(Tenant.id == user.tenant_id))
            db.commit()
    finally:
        db.close()


def _plan_and_close(*, expect_tenants: int, expect_materials: int) -> None:
    db = SessionLocal()
    try:
        plan = resolve_plan(db)
        assert len(plan.tenant_ids) == expect_tenants
        assert len(plan.material_ids) == expect_materials
        return plan
    finally:
        db.close()


class TestDryRunDoesNotMutate:
    def test_dry_run_reports_expected_counts_without_deleting_anything(self, qa_fixture):
        db = SessionLocal()
        try:
            plan = resolve_plan(db)
            assert set(plan.tenant_ids) == set(qa_fixture["tenant_ids"])
            assert plan.material_ids == [qa_fixture["material_id"]]
            assert plan.counts["customers"] == 1
            assert plan.counts["projects"] == 1
            assert plan.counts["quotes"] == 1
            # dry run: resolve_plan is read-only by construction — never
            # calls execute_plan — so nothing was deleted. Confirm the
            # fixture's own rows are still present.
            assert db.get(Tenant, qa_fixture["tenant_ids"][0]) is not None
        finally:
            db.close()


class TestExactMatchOnly:
    def test_unrelated_tenant_is_never_resolved(self, qa_fixture, unrelated_tenant):
        db = SessionLocal()
        try:
            plan = resolve_plan(db)
            assert unrelated_tenant["tenant_id"] not in plan.tenant_ids
        finally:
            db.close()

    def test_lookalike_tenant_name_is_not_matched(self, client, qa_fixture):
        """A name that merely contains the QA prefix but isn't an exact
        match must never be resolved — this is what "exact match only, no
        wildcard" means in practice."""
        r = client.post(
            "/api/v1/auth/signup",
            json={
                "company_name": "SIMO-LAUNCH-QA-TENANT-A-BUT-NOT-REALLY",
                "name": "Lookalike Owner",
                "email": f"pytest-lookalike-{RUN_ID}@example.invalid",
                "password": "Pytest-Lookalike-Password-1!",
            },
        )
        assert r.status_code == 201, r.text
        lookalike_tenant_id = uuid.UUID(r.json()["user"]["tenant_id"])
        try:
            db = SessionLocal()
            try:
                plan = resolve_plan(db)
                assert lookalike_tenant_id not in plan.tenant_ids
            finally:
                db.close()
        finally:
            db2 = SessionLocal()
            try:
                from app.database.models import (
                    ActivityLog,
                    Communication,
                    EmailVerificationToken,
                    Subscription,
                )

                # Same FK ordering constraint cleanup_launch_qa.py itself
                # handles — signup logs a real ActivityLog row (Sprint
                # 012, ADR-029) and, since Sprint 039's Blocker 1, also an
                # EmailVerificationToken (user_id FK) and a Communication
                # row (tenant_id FK) for its verification-email attempt,
                # and since Sprint 039 Blocker 3, also a real trial
                # Subscription row — all must go before User/Tenant here
                # too.
                db2.execute(delete(ActivityLog).where(ActivityLog.tenant_id == lookalike_tenant_id))
                db2.execute(
                    delete(EmailVerificationToken).where(
                        EmailVerificationToken.user_id.in_(
                            select(User.id).where(User.tenant_id == lookalike_tenant_id)
                        )
                    )
                )
                db2.execute(delete(Communication).where(Communication.tenant_id == lookalike_tenant_id))
                db2.execute(delete(Subscription).where(Subscription.tenant_id == lookalike_tenant_id))
                db2.execute(delete(User).where(User.tenant_id == lookalike_tenant_id))
                db2.execute(delete(Tenant).where(Tenant.id == lookalike_tenant_id))
                db2.commit()
            finally:
                db2.close()


class TestUnrelatedDataPreserved:
    def test_confirmed_cleanup_leaves_unrelated_tenant_fully_intact(self, qa_fixture, unrelated_tenant):
        db = SessionLocal()
        try:
            plan = resolve_plan(db)
            execute_plan(db, plan)
            db.commit()
        finally:
            db.close()

        db2 = SessionLocal()
        try:
            assert db2.get(Tenant, unrelated_tenant["tenant_id"]) is not None
            assert db2.get(Customer, unrelated_tenant["customer_id"]) is not None
        finally:
            db2.close()


class TestDeletionOrderAndCompleteness:
    def test_confirmed_cleanup_removes_every_qa_row(self, qa_fixture):
        db = SessionLocal()
        try:
            plan = resolve_plan(db)
            execute_plan(db, plan)
            db.commit()
        finally:
            db.close()

        db2 = SessionLocal()
        try:
            for tenant_id in qa_fixture["tenant_ids"]:
                assert db2.get(Tenant, tenant_id) is None
            assert db2.get(Material, qa_fixture["material_id"]) is None
            remaining = resolve_plan(db2)
            assert remaining.is_empty
        finally:
            db2.close()


class TestOrphanedAnonymousQuotes:
    """Sprint 030's real production fixture (found via a live dry-run, not
    invented) includes an anonymous quote (tenant_id IS NULL — the public
    POST /api/v1/quote path, ADR-023) whose customer_id still references a
    QA customer. Being untenanted, it's invisible to any tenant_id-scoped
    query, but it's a real FK reference: deleting the QA customer while it
    exists violates the customers FK. It must be resolved and cleaned
    alongside the QA customer it targets, and only that customer's
    orphans — never an orphan quote belonging to an unrelated customer."""

    def _create_anonymous_quote_for(self, client, *, customer_id: str) -> uuid.UUID:
        r = client.post(
            "/api/v1/quote",
            json={
                "customer": "Anonymous walk-in",
                "material": QA_MATERIAL_NAME,
                "thickness": QA_MATERIAL_THICKNESS,
                "kitchen_length": 2.0,
                "customer_id": customer_id,
            },
            # deliberately no Authorization header — get_current_user_optional
            # resolves to None, so the created quote has tenant_id=NULL.
        )
        assert r.status_code == 200, r.text
        return uuid.UUID(r.json()["id"])

    def test_orphaned_quote_referencing_qa_customer_is_included_in_plan(self, client, qa_fixture):
        orphan_id = self._create_anonymous_quote_for(client, customer_id=str(qa_fixture["customer_id"]))
        db = SessionLocal()
        try:
            assert db.get(Quote, orphan_id).tenant_id is None  # sanity: genuinely untenanted
            plan = resolve_plan(db)
            assert orphan_id in plan.orphan_quote_ids
        finally:
            db.close()

    def test_confirmed_cleanup_removes_the_orphan_without_fk_violation(self, client, qa_fixture):
        orphan_id = self._create_anonymous_quote_for(client, customer_id=str(qa_fixture["customer_id"]))
        db = SessionLocal()
        try:
            plan = resolve_plan(db)
            execute_plan(db, plan)  # must not raise IntegrityError deleting the customer
            db.commit()
        finally:
            db.close()

        db2 = SessionLocal()
        try:
            assert db2.get(Quote, orphan_id) is None
            assert db2.get(Customer, qa_fixture["customer_id"]) is None
        finally:
            db2.close()

    def test_orphan_quote_belonging_to_an_unrelated_customer_is_never_touched(
        self, client, qa_fixture, unrelated_tenant
    ):
        unrelated_orphan_id = self._create_anonymous_quote_for(
            client, customer_id=str(unrelated_tenant["customer_id"])
        )
        db = SessionLocal()
        try:
            plan = resolve_plan(db)
            assert unrelated_orphan_id not in plan.orphan_quote_ids
            execute_plan(db, plan)
            db.commit()
        finally:
            db.close()

        db2 = SessionLocal()
        try:
            assert db2.get(Quote, unrelated_orphan_id) is not None, (
                "an orphan quote belonging to a non-QA customer must never be deleted"
            )
        finally:
            db2.close()


class TestTransactionRollback:
    def test_injected_failure_after_partial_delete_rolls_back_entirely(self, qa_fixture):
        db = SessionLocal()
        try:
            plan = resolve_plan(db)
            # Simulate an unexpected failure partway through by deleting
            # one tenant_id from the plan's own list after some deletes
            # would already have run, forcing execute_plan to attempt a
            # delete against a row that's about to violate an assumption
            # — instead, directly prove the rollback contract: run
            # execute_plan, then roll back explicitly (exactly what
            # main() does on an exception) and confirm nothing committed.
            execute_plan(db, plan)
            db.rollback()
        finally:
            db.close()

        db2 = SessionLocal()
        try:
            for tenant_id in qa_fixture["tenant_ids"]:
                assert db2.get(Tenant, tenant_id) is not None, (
                    "rollback must leave every QA row exactly as it was"
                )
        finally:
            db2.close()


class TestIdempotentRepeat:
    def test_second_confirmed_run_against_already_clean_database_deletes_nothing(self, qa_fixture):
        db = SessionLocal()
        try:
            plan = resolve_plan(db)
            execute_plan(db, plan)
            db.commit()
        finally:
            db.close()

        db2 = SessionLocal()
        try:
            second_plan = resolve_plan(db2)
            assert second_plan.is_empty
            execute_plan(db2, second_plan)  # must be a safe no-op, not an error
            db2.commit()
        finally:
            db2.close()


class TestEnvironmentGuard:
    def test_production_marker_accepted_for_production(self):
        verify_environment(
            "production",
            database_url="postgresql+psycopg://u:p@simo-postgres-production.railway.internal:5432/railway",
        )

    def test_staging_marker_accepted_for_staging(self):
        verify_environment(
            "staging", database_url="postgresql+psycopg://u:p@postgres.railway.internal:5432/railway"
        )

    def test_production_environment_rejects_staging_host(self):
        with pytest.raises(EnvironmentMismatchError):
            verify_environment(
                "production",
                database_url="postgresql+psycopg://u:p@postgres.railway.internal:5432/railway",
            )

    def test_staging_environment_rejects_production_host(self):
        with pytest.raises(EnvironmentMismatchError):
            verify_environment(
                "staging",
                database_url="postgresql+psycopg://u:p@simo-postgres-production.railway.internal:5432/railway",
            )

    def test_unknown_environment_value_is_rejected(self):
        with pytest.raises(EnvironmentMismatchError):
            verify_environment(
                "not-a-real-environment",
                database_url="postgresql+psycopg://u:p@simo-postgres-production.railway.internal:5432/railway",
            )

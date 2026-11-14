"""QA-UPLOAD-ORPHAN and QA-PARTIAL-COMMIT regression tests.

Both were found by the A1 writer-barrier rehearsal:
* an upload wrote its file before its database row, so any database failure left an
  unreferenced file;
* creating a customer committed the customer, then wrote its activity record in a second
  session, so a failure between them returned an error for a saved customer.
"""

import io
import logging
import uuid
from pathlib import Path

import pytest
from fastapi import UploadFile
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.activity.models import ActivityEventCreate, ActivityType
from app.activity.service import activity_service
from app.core.config import settings
from app.database import crud
from app.database.database import SessionLocal
from app.database.models import ActivityLog, Customer, Document, User
from app.documents.service import document_service
from app.main import app

NAME = "Pytest Integrity Customer"


@pytest.fixture()
def seeded(db, client):  # `client` starts the app, which seeds the owner
    user = db.scalars(select(User).where(User.email == settings.seed_admin_email)).first()
    customer = crud.create_customer(db, id=uuid.uuid4(), tenant_id=user.tenant_id, name=NAME)
    yield user, customer
    db.rollback()
    db.execute(delete(Document).where(Document.customer_id == customer.id))
    db.execute(delete(ActivityLog).where(ActivityLog.description == NAME))
    db.execute(delete(Customer).where(Customer.name.in_([NAME, NAME + " atomic", NAME + " ok"])))
    db.commit()


def files_in_upload_dir() -> set[str]:
    folder = Path(settings.upload_dir)
    return {p.name for p in folder.iterdir()} if folder.exists() else set()


def pdf_upload() -> UploadFile:
    return UploadFile(io.BytesIO(b"%PDF-1.4\n" + b"0" * 64), filename="orphan-test.pdf")


def test_failed_database_insert_leaves_no_file(db, seeded, monkeypatch):
    user, customer = seeded
    before = files_in_upload_dir()

    def boom(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("app.documents.service.crud.create_document", boom)
    with pytest.raises(RuntimeError):
        document_service.upload_document(
            db, tenant_id=user.tenant_id, uploaded_by_user_id=user.id, customer_id=customer.id, file=pdf_upload()
        )
    assert files_in_upload_dir() == before


def test_a_lost_commit_acknowledgement_keeps_the_file_because_the_row_exists(db, seeded, monkeypatch):
    """If COMMIT succeeded but the error came afterwards, deleting the file would leave a dangling row."""
    user, customer = seeded
    real = crud.create_document

    def commit_then_fail(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError("connection lost after commit")

    monkeypatch.setattr("app.documents.service.crud.create_document", commit_then_fail)
    before = files_in_upload_dir()
    with pytest.raises(RuntimeError):
        document_service.upload_document(
            db, tenant_id=user.tenant_id, uploaded_by_user_id=user.id, customer_id=customer.id, file=pdf_upload()
        )
    new_files = files_in_upload_dir() - before
    row = db.scalars(select(Document).where(Document.customer_id == customer.id)).first()
    assert row is not None and new_files == {row.storage_filename}
    (Path(settings.upload_dir) / row.storage_filename).unlink()


def test_a_database_that_cannot_be_asked_keeps_the_file(db, seeded, monkeypatch):
    """Unknown is not 'absent': an orphan is detectable and harmless, a deleted only-copy is not."""
    user, customer = seeded

    def boom(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("app.documents.service.crud.create_document", boom)
    monkeypatch.setattr(db, "rollback", lambda: (_ for _ in ()).throw(RuntimeError("cannot roll back")))
    before = files_in_upload_dir()
    with pytest.raises(RuntimeError):
        document_service.upload_document(
            db, tenant_id=user.tenant_id, uploaded_by_user_id=user.id, customer_id=customer.id, file=pdf_upload()
        )
    kept = files_in_upload_dir() - before
    assert len(kept) == 1
    (Path(settings.upload_dir) / kept.pop()).unlink()


def test_successful_upload_is_unchanged(db, seeded):
    user, customer = seeded
    doc = document_service.upload_document(
        db, tenant_id=user.tenant_id, uploaded_by_user_id=user.id, customer_id=customer.id, file=pdf_upload()
    )
    assert (Path(settings.upload_dir) / doc.storage_filename).read_bytes().startswith(b"%PDF")
    (Path(settings.upload_dir) / doc.storage_filename).unlink()


def test_customer_and_activity_record_are_one_transaction(db, monkeypatch, auth_headers):
    """If the activity record cannot be written, no customer is saved: all or nothing, safe to retry."""

    def boom(*args, **kwargs):
        raise RuntimeError("activity write failed")

    monkeypatch.setattr("app.activity.repository.crud.create_activity_log", boom)
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post("/api/v1/customers", json={"name": NAME + " atomic"}, headers=auth_headers)
    assert r.status_code == 500
    db.rollback()
    assert db.scalars(select(Customer).where(Customer.name == NAME + " atomic")).first() is None


def test_successful_customer_creation_writes_both_records(db, client, auth_headers, seeded):
    r = client.post("/api/v1/customers", json={"name": NAME + " ok"}, headers=auth_headers)
    assert r.status_code == 201
    db.rollback()
    assert len(db.scalars(select(Customer).where(Customer.name == NAME + " ok")).all()) == 1
    assert db.scalars(select(ActivityLog).where(ActivityLog.description == NAME + " ok")).first() is not None


def test_a_standalone_activity_write_failure_cannot_fail_a_committed_request(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise RuntimeError("activity database unavailable")

    monkeypatch.setattr("app.activity.repository.SessionLocal", boom)
    with caplog.at_level(logging.ERROR, logger="simo_os"):
        event = activity_service.log(
            ActivityEventCreate(type=ActivityType.CUSTOMER_ADDED, title="t", description="d"), tenant_id=uuid.uuid4()
        )
    assert event.title == "t"
    assert any("Activity log write failed" in r.getMessage() for r in caplog.records)

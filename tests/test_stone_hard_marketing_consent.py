"""SEC003: absence of recorded optional consent is not affirmative opt-in."""
from types import SimpleNamespace
from unittest.mock import Mock
import uuid
from app.privacy.router import get_marketing_preference


def test_missing_optional_consent_is_off_not_inferred_opt_in():
    db = Mock()
    db.scalars.return_value.first.return_value = None
    user = SimpleNamespace(tenant_id=uuid.uuid4(), email='Synthetic@Example.Invalid')
    result = get_marketing_preference(current_user=user, db=db)
    assert result.enabled is False
    assert result.source == 'default'
    assert result.updated_at is None


def test_explicit_existing_opt_in_or_opt_out_is_preserved():
    db = Mock()
    user = SimpleNamespace(tenant_id=uuid.uuid4(), email='synthetic@example.invalid')
    for enabled in [True, False]:
        db.scalars.return_value.first.return_value = SimpleNamespace(enabled=enabled, source='authenticated_preferences', updated_at=None)
        assert get_marketing_preference(current_user=user, db=db).enabled is enabled

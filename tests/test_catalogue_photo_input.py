import pytest
from pydantic import ValidationError
from app.catalogue.models import TenantOverrideIn

@pytest.mark.parametrize('url', ['javascript:alert(1)', 'http://example.com/photo.jpg', 'https://user:secret@example.com/photo.jpg'])
def test_material_photo_rejects_unsafe_urls(url):
    with pytest.raises(ValidationError):
        TenantOverrideIn(image_url=url)

def test_material_photo_accepts_https_owner_source():
    assert TenantOverrideIn(image_url='https://example.com/stone.jpg').image_url == 'https://example.com/stone.jpg'

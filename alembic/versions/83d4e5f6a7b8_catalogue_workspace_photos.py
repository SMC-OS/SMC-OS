"""Optional workspace-owned material photographs; no global photos imported."""
from alembic import op
import sqlalchemy as sa
revision = '83d4e5f6a7b8'
down_revision = '72b390ac61e4'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('tenant_catalogue_overrides', sa.Column('image_url', sa.String(2048), nullable=True))

def downgrade():
    op.drop_column('tenant_catalogue_overrides', 'image_url')

"""merge heads

Revision ID: f353becf4875
Revises: 5c2785cb9bfa, abc123def456
Create Date: 2026-02-09 00:30:30.020905

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f353becf4875'
down_revision = ('5c2785cb9bfa', 'abc123def456')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass

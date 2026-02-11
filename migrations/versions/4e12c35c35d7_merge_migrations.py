"""merge migrations

Revision ID: 4e12c35c35d7
Revises: add_farmer_response, add_message_model
Create Date: 2026-02-10 15:32:10.228132

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4e12c35c35d7'
down_revision = ('add_farmer_response', 'add_message_model')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass

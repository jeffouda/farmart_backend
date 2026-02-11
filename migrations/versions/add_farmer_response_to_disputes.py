"""Add farmer response fields to disputes

Revision ID: add_farmer_response
Revises: 7efc2370a9cc
Create Date: 2026-02-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_farmer_response'
down_revision = '7efc2370a9cc'
branch_labels = None
depends_on = None


def upgrade():
    # Add farmer response columns to disputes table
    op.add_column('disputes', sa.Column('farmer_response', sa.Text(), nullable=True))
    op.add_column('disputes', sa.Column('farmer_response_at', sa.DateTime(), nullable=True))
    op.add_column('disputes', sa.Column('farmer_evidence', sa.String(255), nullable=True))


def downgrade():
    op.drop_column('disputes', 'farmer_response')
    op.drop_column('disputes', 'farmer_response_at')
    op.drop_column('disputes', 'farmer_evidence')

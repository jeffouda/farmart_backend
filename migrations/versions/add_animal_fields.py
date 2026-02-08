"""Add gender and health_history to animals table

Revision ID: abc123def456
Revises: bab4396ce7e6
Create Date: 2026-02-08

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'abc123def456'
down_revision = 'bab4396ce7e6'
branch_labels = None
depends_on = None


def upgrade():
    # Add gender column
    op.add_column('animals', sa.Column('gender', sa.String(20), nullable=True))
    
    # Add health_history column
    op.add_column('animals', sa.Column('health_history', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('animals', 'health_history')
    op.drop_column('animals', 'gender')

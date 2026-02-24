"""Add quantity field to Animal model

Revision ID: add_quantity_to_animals
Revises: latest
Create Date: 2026-02-13

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_quantity_to_animals'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Add quantity column to animals table
    op.add_column('animals', sa.Column('quantity', sa.Integer(), nullable=False, default=1))
    
    # Update existing records to have quantity = 1
    op.execute("UPDATE animals SET quantity = 1 WHERE quantity IS NULL")

def downgrade():
    # Remove quantity column
    op.drop_column('animals', 'quantity')

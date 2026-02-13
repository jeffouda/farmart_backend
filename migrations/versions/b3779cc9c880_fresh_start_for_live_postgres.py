"""Fresh start for live postgres

Revision ID: b3779cc9c880
Revises: 
Create Date: 2026-02-13 07:13:06.963463

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# Import your custom UUIDType if you need it, 
# but for Postgres, the native dialect is safer
from app.models import UUIDType 

# revision identifiers, used by Alembic.
revision = 'b3779cc9c880'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Note: If your tables DON'T exist, use op.create_table. 
    # If they DO exist but have wrong types, we use the logic below.
    
    # We use a loop to handle the repetitive UUID conversions
    tables_to_fix = [
        ('users', ['id']),
        ('animals', ['id', 'farmer_id']),
        ('farmers', ['id', 'user_id']),
        ('buyers', ['id', 'user_id']),
        ('orders', ['id', 'buyer_id', 'farmer_id']),
        ('notifications', ['id', 'user_id']),
        ('disputes', ['id', 'order_id']),
        ('reviews', ['id', 'order_id', 'reviewer_id', 'target_id']),
        ('wishlists', ['user_id', 'animal_id']),
        ('messages', ['sender_id', 'receiver_id', 'livestock_id']),
        ('bargain_sessions', ['animal_id', 'buyer_id', 'farmer_id']),
        ('bargain_messages', ['sender_id']),
        ('escrow_records', ['id', 'order_id'])
    ]

    for table, columns in tables_to_fix:
        for col in columns:
            op.execute(f'ALTER TABLE {table} ALTER COLUMN {col} TYPE UUID USING {col}::text::uuid')

def downgrade():
    # To revert, we'd convert back to numeric, though usually unnecessary for a fresh start
    pass
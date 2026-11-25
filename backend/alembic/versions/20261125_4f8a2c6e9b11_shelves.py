"""shelves: where each product is kept in the shop

Adds the shelves table (one list per shop, codes unique within the shop) and an
optional products.shelf_id. Deleting a shelf leaves its products without a shelf.

Revision ID: 4f8a2c6e9b11
Revises: 9b3f6e2d4a17
Create Date: 2026-11-25 09:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '4f8a2c6e9b11'
down_revision: Union[str, None] = '9b3f6e2d4a17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('shelves',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=30), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('area', sa.String(length=60), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('shop_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name='fk_shelves_shop_id_shops', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_shelves')),
    sa.UniqueConstraint('shop_id', 'code', name='uq_shelves_shop_code')
    )
    op.create_index('ix_shelves_shop_id', 'shelves', ['shop_id'], unique=False)
    op.add_column('products', sa.Column('shelf_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_products_shelf_id_shelves', 'products', 'shelves', ['shelf_id'], ['id'], ondelete='SET NULL')
    op.create_index('ix_products_shelf_id', 'products', ['shelf_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_products_shelf_id', table_name='products')
    op.drop_constraint('fk_products_shelf_id_shelves', 'products', type_='foreignkey')
    op.drop_column('products', 'shelf_id')
    op.drop_index('ix_shelves_shop_id', table_name='shelves')
    op.drop_table('shelves')

"""shops: every business gets its own private data

Adds the shops table and a shop_id column to every table that holds a shop's
data. Rows that already exist are moved into one shop called "My shop", so an
existing database keeps working. Codes, SKUs and PO numbers become unique per
shop instead of across the whole database. calendar_days stays shared.

Revision ID: 7d2e4b9a1c30
Revises: 5c7941a3cf1d
Create Date: 2026-11-01 12:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '7d2e4b9a1c30'
down_revision: Union[str, None] = '5c7941a3cf1d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every table whose rows belong to one shop (app_settings is handled separately: shop_id joins its key).
SHOP_TABLES = [
    'users', 'categories', 'suppliers', 'products', 'inventory_balances', 'inventory_transactions',
    'daily_sales', 'purchase_orders', 'purchase_order_items', 'forecast_runs', 'forecasts',
    'model_evaluations', 'recommendation_runs', 'reorder_recommendations', 'simulation_runs', 'import_jobs',
]
# (table, old unique constraint, old columns, new name, new columns)
UNIQUES = [
    ('categories', 'uq_categories_code', ['code'], 'uq_categories_shop_code', ['shop_id', 'code']),
    ('suppliers', 'uq_suppliers_code', ['code'], 'uq_suppliers_shop_code', ['shop_id', 'code']),
    ('products', 'uq_products_sku', ['sku'], 'uq_products_shop_sku', ['shop_id', 'sku']),
    ('purchase_orders', 'uq_purchase_orders_po_number', ['po_number'],
     'uq_purchase_orders_shop_po_number', ['shop_id', 'po_number']),
    ('model_evaluations', 'uq_model_evaluations_key',
     ['model_name', 'model_version', 'period', 'horizon_days', 'demand_class'],
     'uq_model_evaluations_key', ['shop_id', 'model_name', 'model_version', 'period', 'horizon_days', 'demand_class']),
]


def _add_shop_column(table: str, index: bool = True) -> None:
    op.add_column(table, sa.Column('shop_id', sa.Integer(), nullable=True))
    op.execute(f"UPDATE {table} SET shop_id = 1")
    op.alter_column(table, 'shop_id', nullable=False)
    op.create_foreign_key(f'fk_{table}_shop_id_shops', table, 'shops', ['shop_id'], ['id'], ondelete='CASCADE')
    if index:
        op.create_index(f'ix_{table}_shop_id', table, ['shop_id'], unique=False)


def upgrade() -> None:
    op.create_table('shops',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_shops'))
    )
    # Existing data (from before shops existed) becomes shop 1. An empty database gets no shop.
    checks = " OR ".join(f"EXISTS (SELECT 1 FROM {t})" for t in [*SHOP_TABLES, 'app_settings'])
    op.execute(f"INSERT INTO shops (id, name, is_demo) SELECT 1, 'My shop', false WHERE {checks}")
    op.execute("SELECT setval(pg_get_serial_sequence('shops', 'id'), COALESCE((SELECT MAX(id) FROM shops), 0) + 1, false)")

    for table in SHOP_TABLES:
        _add_shop_column(table)

    _add_shop_column('app_settings', index=False)
    op.drop_constraint('pk_app_settings', 'app_settings', type_='primary')
    op.create_primary_key('pk_app_settings', 'app_settings', ['shop_id', 'key'])

    for table, old, _, new, columns in UNIQUES:
        op.drop_constraint(old, table, type_='unique')
        op.create_unique_constraint(new, table, columns)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM shops")).scalar() > 1:
        raise RuntimeError("Cannot downgrade: the database holds more than one shop's data")
    for table, old, old_columns, new, _ in reversed(UNIQUES):
        op.drop_constraint(new, table, type_='unique')
        op.create_unique_constraint(old, table, old_columns)
    op.drop_constraint('pk_app_settings', 'app_settings', type_='primary')
    op.create_primary_key('pk_app_settings', 'app_settings', ['key'])
    op.drop_constraint('fk_app_settings_shop_id_shops', 'app_settings', type_='foreignkey')
    op.drop_column('app_settings', 'shop_id')
    for table in reversed(SHOP_TABLES):
        op.drop_index(f'ix_{table}_shop_id', table_name=table)
        op.drop_constraint(f'fk_{table}_shop_id_shops', table, type_='foreignkey')
        op.drop_column(table, 'shop_id')
    op.drop_table('shops')

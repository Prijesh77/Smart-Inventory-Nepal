"""drop simulation_runs: the research policy simulation is not part of the product

The table held runs of the capstone's M5-based inventory simulation (Analytics
page). The product no longer has that feature. Downgrade recreates the empty table.

Revision ID: 9b3f6e2d4a17
Revises: 7d2e4b9a1c30
Create Date: 2026-11-01 18:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '9b3f6e2d4a17'
down_revision: Union[str, None] = '7d2e4b9a1c30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('simulation_runs')


def downgrade() -> None:
    op.create_table('simulation_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('status', sa.Enum('pending', 'running', 'completed', 'failed', name='simulation_run_status', native_enum=False, create_constraint=True, length=30), nullable=False),
    sa.Column('params', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('results', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('created_by', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('shop_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_simulation_runs_created_by_users')),
    sa.ForeignKeyConstraint(['shop_id'], ['shops.id'], name='fk_simulation_runs_shop_id_shops', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_simulation_runs'))
    )
    op.create_index('ix_simulation_runs_shop_id', 'simulation_runs', ['shop_id'], unique=False)

"""add_component_type_and_pricing_rules_to_price_variants

Revision ID: f99c8e24ec13
Revises: 268229712326
Create Date: 2026-04-23 10:53:06.944112

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f99c8e24ec13'
down_revision = '268229712326'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Add nullable column first (existing rows have no value)
    op.add_column('price_variants', sa.Column('component_type', sa.String(length=20), nullable=True, comment='柜身 / 门板 / 护墙 / 见光板 / 抽面'))
    op.add_column('price_variants', sa.Column('min_charge_area', sa.DECIMAL(precision=5, scale=3), nullable=True, comment='最低计价面积（㎡），如 0.1 / 0.2 / 0.3 / 0.5'))
    op.add_column('price_variants', sa.Column('applicable_models', postgresql.ARRAY(sa.Text()), nullable=True, comment="可做门型列表，如 ['MX-A01','MX-A02']"))

    # Step 2: Backfill existing rows with default component_type
    op.execute("UPDATE price_variants SET component_type = '门板' WHERE component_type IS NULL")

    # Step 3: Now make it NOT NULL
    op.alter_column('price_variants', 'component_type', nullable=False)


def downgrade() -> None:
    op.drop_column('price_variants', 'applicable_models')
    op.drop_column('price_variants', 'min_charge_area')
    op.drop_column('price_variants', 'component_type')

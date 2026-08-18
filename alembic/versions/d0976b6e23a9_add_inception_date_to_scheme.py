"""add_inception_date_to_scheme

Revision ID: d0976b6e23a9
Revises: 
Create Date: 2026-08-03 19:49:58.471646
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd0976b6e23a9'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add inception_date column to scheme table with index."""
    # Add nullable inception_date column of type Date
    with op.batch_alter_table('scheme', schema=None) as batch_op:
        batch_op.add_column(sa.Column('inception_date', sa.Date(), nullable=True))
        batch_op.create_index('ix_scheme_inception_date', ['inception_date'], unique=False)


def downgrade() -> None:
    """Remove inception_date column and index from scheme table."""
    with op.batch_alter_table('scheme', schema=None) as batch_op:
        batch_op.drop_index('ix_scheme_inception_date')
        batch_op.drop_column('inception_date')

"""university aliases

Revision ID: c5cd1dc29634
Revises: 8f3e45fe9887
Create Date: 2026-10-29 19:50:24.339973

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c5cd1dc29634'
down_revision: Union[str, Sequence[str], None] = '8f3e45fe9887'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('universities', sa.Column('aliases', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('universities', 'aliases')

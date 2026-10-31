"""study plan on the profile; app_settings for UI-configured LLM providers

Revision ID: a1b2c3d4e5f6
Revises: 19fe45a50a75
Create Date: 2026-10-31 13:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '19fe45a50a75'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('candidate_profiles', sa.Column('target_degrees', postgresql.JSONB(astext_type=sa.Text()),
                                                  nullable=False, server_default='["thesis_masters", "phd"]'))
    op.add_column('candidate_profiles', sa.Column('target_countries', postgresql.JSONB(astext_type=sa.Text()),
                                                  nullable=False, server_default='["US", "CA"]'))
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(), primary_key=True),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('app_settings')
    op.drop_column('candidate_profiles', 'target_countries')
    op.drop_column('candidate_profiles', 'target_degrees')

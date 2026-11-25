"""add_company_website_unique_index

Revision ID: 03e1377df421
Revises: e5915e5f7d45
Create Date: 2026-11-24 02:56:41.415475

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '03e1377df421'
down_revision: Union[str, Sequence[str], None] = 'e5915e5f7d45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema: partial unique index enforcing case-insensitive scheme and hostname
    while strictly preserving path, query, and fragment case, and normalizing trailing slashes.
    """
    op.create_index(
        'uq_companies_active_website_canonical',
        'companies',
        [sa.text("(lower(substring(website_url from '^([a-zA-Z]+://[^/?#]+)')) || regexp_replace(coalesce(substring(website_url from '^[a-zA-Z]+://[^/?#]+(.*)$'), ''), '/+(?=[?#]|$)', '', 'g'))")],
        unique=True,
        postgresql_where=sa.text('is_deleted = false')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        'uq_companies_active_website_canonical',
        table_name='companies',
        postgresql_where=sa.text('is_deleted = false')
    )

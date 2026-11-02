"""Store analyst-owned business context for gap analysis.

Revision ID: ab72c0e419d3
Revises: 8c1f2a9d3e47
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "ab72c0e419d3"
down_revision = "8c1f2a9d3e47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("gap_context", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "gap_context")

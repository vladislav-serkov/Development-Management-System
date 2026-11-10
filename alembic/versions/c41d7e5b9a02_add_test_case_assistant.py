"""Add test-case assistant sessions and stable test-case ids.

Revision ID: c41d7e5b9a02
Revises: ab72c0e419d3
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "c41d7e5b9a02"
down_revision = "ab72c0e419d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("feature_id", sa.BigInteger(), sa.ForeignKey("features.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_assistant_sessions_feature_id", "assistant_sessions", ["feature_id"])
    op.create_table(
        "assistant_turns",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "session_pk", sa.BigInteger(),
            sa.ForeignKey("assistant_sessions.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("turn_id", sa.Text(), nullable=False, unique=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_assistant_turns_session_pk", "assistant_turns", ["session_pk"])
    # The assistant addresses test cases by a stable id, not by list position.
    op.execute(
        "UPDATE analysis_items "
        "SET data = data || jsonb_build_object('id', substr(md5(random()::text || id::text), 1, 12)) "
        "WHERE kind = 'test_case' AND NOT (data ? 'id')"
    )


def downgrade() -> None:
    op.drop_table("assistant_turns")
    op.drop_table("assistant_sessions")

"""Drop Java-autotest state from test cases (replaced by ru-dsl scripts).

«Принять» now writes a ru-dsl-v2 scenario (`script_*` keys) instead of a Java
autotest in flp-autotests; the old `autotest_*` keys are dead data the API would
keep serving. Review statuses and `tasks` history rows are left as they are.

Revision ID: d52e8f6a1b03
Revises: c41d7e5b9a02
"""
from alembic import op

revision = "d52e8f6a1b03"
down_revision = "c41d7e5b9a02"
branch_labels = None
depends_on = None

AUTOTEST_KEYS = (
    "autotest_status", "autotest_error", "autotest_requested_at", "autotest_started_at",
    "autotest_finished_at", "autotest_log", "autotest_branch", "autotest_mr_url", "autotest_summary",
)


def upgrade() -> None:
    keys = ", ".join(f"'{key}'" for key in AUTOTEST_KEYS)
    op.execute(
        f"UPDATE analysis_items SET data = data - ARRAY[{keys}] "
        "WHERE kind = 'test_case' AND data ? 'autotest_status'"
    )


def downgrade() -> None:
    # The removed keys described autotests of a flow that no longer exists.
    pass

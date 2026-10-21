"""Establish a schema baseline without business data."""

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM ashana_app")


def downgrade() -> None:
    pass

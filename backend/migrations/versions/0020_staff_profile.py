"""Staff Telegram contact and archiving instead of deleting referenced accounts."""

from alembic import op

revision = "0020_staff_profile"
down_revision = "0019_directory_edit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE identity_users
            ADD COLUMN telegram VARCHAR(33)
                CONSTRAINT ck_identity_telegram CHECK (telegram ~ '^@[A-Za-z0-9_]{5,32}$'),
            ADD COLUMN deleted_at TIMESTAMPTZ;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE identity_users DROP COLUMN telegram, DROP COLUMN deleted_at")

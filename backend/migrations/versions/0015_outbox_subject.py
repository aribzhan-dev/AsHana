"""Link staff notifications to their order without putting the id in the text."""

from alembic import op

revision = "0015_outbox_subject"
down_revision = "0014_realtime"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE notification_outbox ADD COLUMN subject_id UUID;
        CREATE INDEX ix_notification_outbox_subject ON notification_outbox (subject_id);
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE notification_outbox DROP COLUMN subject_id")

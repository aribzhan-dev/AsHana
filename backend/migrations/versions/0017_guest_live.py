"""Route order change signals to the guest who owns the order."""

from alembic import op

revision = "0017_guest_live"
down_revision = "0016_finance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The guest id stays inside the server: the listener uses it to pick the socket.
    op.execute("""
        CREATE OR REPLACE FUNCTION ashana_notify_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_TABLE_NAME = 'order_events' THEN
                PERFORM pg_notify('ashana_events', json_build_object(
                    'topic', 'orders', 'kind', NEW.kind, 'id', NEW.subject_id,
                    'guest', (SELECT guest_id FROM checkout_drafts WHERE id = NEW.subject_id)
                )::text);
            ELSIF TG_TABLE_NAME = 'pos_attempts' THEN
                PERFORM pg_notify('ashana_events', json_build_object(
                    'topic', 'pos', 'kind', NEW.outcome, 'id', NEW.id)::text);
            ELSE
                PERFORM pg_notify('ashana_events', '{"topic":"stock"}');
            END IF;
            RETURN NULL;
        END $$;
    """)


def downgrade() -> None:
    raise RuntimeError("Используйте 0014_realtime для прежней функции")

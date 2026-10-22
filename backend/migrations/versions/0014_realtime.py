"""Change signals for live staff screens via PostgreSQL NOTIFY."""

from alembic import op

revision = "0014_realtime"
down_revision = "0013_operations_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NOTIFY is delivered only after commit, so screens never see rolled-back changes.
    # Payloads carry no personal data or pickup codes: screens reload state over HTTP.
    op.execute("""
        CREATE FUNCTION ashana_notify_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_TABLE_NAME = 'order_events' THEN
                PERFORM pg_notify('ashana_events', json_build_object(
                    'topic', 'orders', 'kind', NEW.kind, 'id', NEW.subject_id)::text);
            ELSIF TG_TABLE_NAME = 'pos_attempts' THEN
                PERFORM pg_notify('ashana_events', json_build_object(
                    'topic', 'pos', 'kind', NEW.outcome, 'id', NEW.id)::text);
            ELSE
                PERFORM pg_notify('ashana_events', '{"topic":"stock"}');
            END IF;
            RETURN NULL;
        END $$;
        CREATE TRIGGER tr_order_events_notify AFTER INSERT ON order_events
            FOR EACH ROW EXECUTE FUNCTION ashana_notify_change();
        CREATE TRIGGER tr_pos_attempts_notify AFTER INSERT ON pos_attempts
            FOR EACH ROW EXECUTE FUNCTION ashana_notify_change();
        CREATE TRIGGER tr_inventory_movements_notify AFTER INSERT ON inventory_movements
            FOR EACH STATEMENT EXECUTE FUNCTION ashana_notify_change();
        CREATE TRIGGER tr_catalog_entries_notify AFTER INSERT OR UPDATE ON catalog_entries
            FOR EACH STATEMENT EXECUTE FUNCTION ashana_notify_change();
    """)


def downgrade() -> None:
    op.execute("""
        DROP TRIGGER tr_catalog_entries_notify ON catalog_entries;
        DROP TRIGGER tr_inventory_movements_notify ON inventory_movements;
        DROP TRIGGER tr_pos_attempts_notify ON pos_attempts;
        DROP TRIGGER tr_order_events_notify ON order_events;
        DROP FUNCTION ashana_notify_change();
    """)

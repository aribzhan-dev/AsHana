"""Add pickup verification and audited consumption of finished reservations."""

import secrets

import sqlalchemy as sa
from alembic import op

revision = "0008_kitchen"
down_revision = "0007_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("checkout_drafts", sa.Column("pickup_code", sa.String(8)))
    op.create_check_constraint(
        "ck_pickup_code", "checkout_drafts", "pickup_code IS NULL OR pickup_code ~ '^[0-9A-F]{8}$'"
    )
    connection = op.get_bind()
    for row in connection.execute(
        sa.text("SELECT id FROM checkout_drafts WHERE status IN ('confirmed','preparing','ready')")
    ):
        connection.execute(
            sa.text("UPDATE checkout_drafts SET pickup_code=:code WHERE id=:id"),
            {"id": row.id, "code": secrets.token_hex(4).upper()},
        )
    op.drop_constraint("ck_inventory_movement_action", "inventory_movements", type_="check")
    op.create_check_constraint(
        "ck_inventory_movement_action",
        "inventory_movements",
        "action IN ('receipt','write_off','count','suspend','resume',"
        "'production_consume','production_output','mock_fulfil')",
    )
    op.drop_constraint("ck_reservation_event", "inventory_reservation_events", type_="check")
    op.create_check_constraint(
        "ck_reservation_event",
        "inventory_reservation_events",
        "action IN ('reserve','release','consume') AND quantity > 0",
    )


def downgrade() -> None:
    raise RuntimeError("Откат выдачи требует плана сохранения истории и кодов получения")

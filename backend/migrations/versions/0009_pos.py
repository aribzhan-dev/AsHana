"""Add immutable demo counter attempts and finished stock sale movements."""

from alembic import op

revision = "0009_pos"
down_revision = "0008_kitchen"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE pos_attempts (
            id UUID PRIMARY KEY,
            actor_id UUID NOT NULL REFERENCES identity_users(id),
            outcome VARCHAR(10) NOT NULL,
            mode VARCHAR(10) NOT NULL,
            currency VARCHAR(3) NOT NULL,
            total_minor BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            lines JSONB NOT NULL,
            CONSTRAINT ck_pos_mode CHECK (outcome IN ('success','failed','timeout')
                AND mode = 'mock' AND currency = 'KZT'),
            CONSTRAINT ck_pos_total CHECK (total_minor BETWEEN 0 AND 99999999999900),
            CONSTRAINT ck_pos_lines CHECK (jsonb_typeof(lines) = 'array'
                AND jsonb_array_length(lines) BETWEEN 1 AND 100)
        )
    """)
    op.execute("CREATE INDEX ix_pos_attempts_created_at ON pos_attempts(created_at)")
    op.execute("REVOKE UPDATE, DELETE ON pos_attempts FROM ashana_app")
    op.drop_constraint("ck_inventory_movement_action", "inventory_movements", type_="check")
    op.create_check_constraint(
        "ck_inventory_movement_action",
        "inventory_movements",
        "action IN ('receipt','write_off','count','suspend','resume',"
        "'production_consume','production_output','mock_fulfil','mock_pos_sale')",
    )


def downgrade() -> None:
    raise RuntimeError("Откат кассы требует плана сохранения истории продаж")

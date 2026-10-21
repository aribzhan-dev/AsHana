"""Add stock items, batches, immutable movements and idempotent operation audit."""

from alembic import op

revision = "0004_inventory"
down_revision = "0003_staff_login"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE inventory_items (
            id UUID NOT NULL,
            name VARCHAR(100) NOT NULL,
            name_key VARCHAR(200) NOT NULL,
            kind VARCHAR(20) NOT NULL,
            unit VARCHAR(10) NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT ck_inventory_item_unit CHECK ((kind='raw' AND unit IN ('kg','l')) OR
        (kind='purchased' AND unit='pcs') OR (kind='prepared' AND unit IN ('pcs','portion'))),
            CONSTRAINT ck_inventory_item_name CHECK (char_length(name) BETWEEN 1 AND 100),
            CONSTRAINT uq_inventory_item_unit UNIQUE (id, unit),
            UNIQUE (name_key)
        )
    """)
    op.execute("""
        CREATE TABLE inventory_audit (
            id UUID NOT NULL,
            actor_id UUID NOT NULL,
            action VARCHAR(30) NOT NULL,
            subject_id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(actor_id) REFERENCES identity_users (id)
        )
    """)
    op.execute("""
        CREATE TABLE inventory_batches (
            id UUID NOT NULL,
            item_id UUID NOT NULL,
            unit VARCHAR(10) NOT NULL,
            label VARCHAR(100) NOT NULL,
            on_hand NUMERIC(18, 6) NOT NULL,
            reserved NUMERIC(18, 6) NOT NULL,
            status VARCHAR(20) NOT NULL,
            version INTEGER NOT NULL,
            total_cost_minor BIGINT NOT NULL,
            received_at TIMESTAMP WITH TIME ZONE NOT NULL,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            source VARCHAR(200) NOT NULL,
            actor_id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(item_id, unit) REFERENCES inventory_items (id, unit),
            CONSTRAINT ck_inventory_stock CHECK (on_hand >= reserved AND reserved >= 0 AND
        on_hand <= 999999999),
            CONSTRAINT ck_inventory_whole_goods CHECK (unit NOT IN ('pcs','portion') OR
        (on_hand=trunc(on_hand) AND reserved=trunc(reserved))),
            CONSTRAINT ck_inventory_state CHECK (status IN
        ('active','suspended','written_off') AND (status != 'written_off' OR on_hand=0)),
            CONSTRAINT ck_inventory_values CHECK (version > 0 AND total_cost_minor BETWEEN 0
        AND 999999999999),
            CONSTRAINT ck_inventory_expiry CHECK (expires_at > received_at),
            FOREIGN KEY(actor_id) REFERENCES identity_users (id)
        )
    """)
    op.execute("""
        CREATE TABLE inventory_requests (
            actor_id UUID NOT NULL,
            operation VARCHAR(30) NOT NULL,
            key UUID NOT NULL,
            fingerprint VARCHAR(64) NOT NULL,
            subject_id UUID NOT NULL,
            version INTEGER NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            PRIMARY KEY (actor_id, operation, key),
            FOREIGN KEY(actor_id) REFERENCES identity_users (id)
        )
    """)
    op.execute("""
        CREATE TABLE inventory_movements (
            id UUID NOT NULL,
            batch_id UUID NOT NULL,
            action VARCHAR(20) NOT NULL,
            delta NUMERIC(18, 6) NOT NULL,
            before NUMERIC(18, 6) NOT NULL,
            after NUMERIC(18, 6) NOT NULL,
            reason VARCHAR(200) NOT NULL,
            actor_id UUID NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            version INTEGER NOT NULL,
            status_before VARCHAR(20) NOT NULL,
            status_after VARCHAR(20) NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT uq_inventory_movement_version UNIQUE (batch_id, version),
            CONSTRAINT ck_inventory_movement_balance CHECK ("before" + delta = "after" AND
        "before" >= 0 AND "after" >= 0),
            CONSTRAINT ck_inventory_movement_action CHECK (action IN
        ('receipt','write_off','count','suspend','resume')),
            FOREIGN KEY(batch_id) REFERENCES inventory_batches (id),
            FOREIGN KEY(actor_id) REFERENCES identity_users (id)
        )
    """)
    op.execute("""
        CREATE INDEX ix_inventory_movements_batch_id ON inventory_movements (batch_id)
    """)
    op.execute("""
        REVOKE UPDATE, DELETE ON inventory_items FROM ashana_app
    """)
    op.execute("""
        REVOKE UPDATE, DELETE ON inventory_movements FROM ashana_app
    """)
    op.execute("""
        REVOKE UPDATE, DELETE ON inventory_audit FROM ashana_app
    """)
    op.execute("""
        REVOKE UPDATE, DELETE ON inventory_requests FROM ashana_app
    """)
    op.execute("""
        REVOKE DELETE ON inventory_batches FROM ashana_app
    """)


def downgrade() -> None:
    raise RuntimeError("Откат склада требует отдельного плана сохранения движений")

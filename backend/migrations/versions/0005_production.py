"""Add immutable recipes and confirmed production linked to stock movements."""

from alembic import op

revision = "0005_production"
down_revision = "0004_inventory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE production_recipes (
        id UUID NOT NULL,
        output_item_id UUID NOT NULL,
        version INTEGER NOT NULL,
        expected_yield INTEGER NOT NULL,
        portion_quantity NUMERIC(18, 6) NOT NULL,
        portion_unit VARCHAR(10) NOT NULL,
        instructions VARCHAR(2000) NOT NULL,
        actor_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT uq_production_recipe_version UNIQUE (output_item_id, version),
        CONSTRAINT ck_production_yield CHECK (version > 0 AND expected_yield BETWEEN 1 AND
        999999999),
        CONSTRAINT ck_production_portion CHECK (portion_quantity > 0 AND portion_quantity <=
        999999999 AND portion_unit IN ('kg','l')),
        FOREIGN KEY(output_item_id) REFERENCES inventory_items (id),
        FOREIGN KEY(actor_id) REFERENCES identity_users (id)
        )
    """)
    op.execute("""
        CREATE TABLE production_batches (
        id UUID NOT NULL,
        recipe_id UUID NOT NULL,
        actual_yield INTEGER NOT NULL,
        actor_id UUID NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT ck_production_actual_yield CHECK (actual_yield BETWEEN 1 AND 999999999),
        FOREIGN KEY(id) REFERENCES inventory_batches (id),
        FOREIGN KEY(recipe_id) REFERENCES production_recipes (id),
        FOREIGN KEY(actor_id) REFERENCES identity_users (id)
        )
    """)
    op.execute("""
        CREATE INDEX ix_production_batches_recipe_id ON production_batches (recipe_id)
    """)
    op.execute("""
        CREATE TABLE production_recipe_lines (
        recipe_id UUID NOT NULL,
        item_id UUID NOT NULL,
        quantity NUMERIC(18, 6) NOT NULL,
        unit VARCHAR(10) NOT NULL,
        PRIMARY KEY (recipe_id, item_id),
        FOREIGN KEY(item_id, unit) REFERENCES inventory_items (id, unit),
        CONSTRAINT ck_production_line CHECK (quantity > 0 AND quantity <= 999999999 AND unit IN
        ('kg','l')),
        FOREIGN KEY(recipe_id) REFERENCES production_recipes (id)
        )
    """)
    op.execute("""
        CREATE TABLE production_consumption (
        production_id UUID NOT NULL,
        batch_id UUID NOT NULL,
        quantity NUMERIC(18, 6) NOT NULL,
        unit VARCHAR(10) NOT NULL,
        item_id UUID NOT NULL,
        movement_id UUID NOT NULL,
        PRIMARY KEY (production_id, batch_id),
        FOREIGN KEY(item_id, unit) REFERENCES inventory_items (id, unit),
        CONSTRAINT ck_production_consumption CHECK (quantity > 0 AND quantity <= 999999999 AND
        unit IN ('kg','l')),
        FOREIGN KEY(production_id) REFERENCES production_batches (id),
        FOREIGN KEY(batch_id) REFERENCES inventory_batches (id),
        UNIQUE (movement_id),
        FOREIGN KEY(movement_id) REFERENCES inventory_movements (id)
        )
    """)
    op.execute("""
        ALTER TABLE inventory_movements DROP CONSTRAINT ck_inventory_movement_action
    """)
    op.execute("""
        ALTER TABLE inventory_movements ADD CONSTRAINT ck_inventory_movement_action CHECK
        (action IN ('receipt','write_off','count','suspend','resume',
        'production_consume','production_output'))
    """)
    op.execute("""
        REVOKE UPDATE, DELETE ON production_recipes FROM ashana_app
    """)
    op.execute("""
        REVOKE UPDATE, DELETE ON production_recipe_lines FROM ashana_app
    """)
    op.execute("""
        REVOKE UPDATE, DELETE ON production_batches FROM ashana_app
    """)
    op.execute("""
        REVOKE UPDATE, DELETE ON production_consumption FROM ashana_app
    """)


def downgrade() -> None:
    raise RuntimeError("Откат производства требует плана сохранения рецептов и движений")

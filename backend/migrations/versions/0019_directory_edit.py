"""Settings entries can be renamed and, while unused, deleted."""

from alembic import op

revision = "0019_directory_edit"
down_revision = "0018_item_images"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Foreign keys from invoices, sales and expenses still forbid deleting a used entry.
    op.execute("GRANT UPDATE (name, name_key), DELETE ON inventory_directories TO ashana_app")


def downgrade() -> None:
    op.execute("REVOKE UPDATE (name, name_key), DELETE ON inventory_directories FROM ashana_app")

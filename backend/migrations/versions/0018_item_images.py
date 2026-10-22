"""Product photos stored in the database, re-encoded by the server."""

from alembic import op

revision = "0018_item_images"
down_revision = "0017_guest_live"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE inventory_item_images (
            item_id UUID PRIMARY KEY REFERENCES inventory_items(id),
            content_type VARCHAR(20) NOT NULL CHECK(content_type = 'image/webp'),
            data BYTEA NOT NULL CHECK(octet_length(data) BETWEEN 1 AND 1048576),
            digest VARCHAR(64) NOT NULL,
            actor_id UUID NOT NULL REFERENCES identity_users(id),
            updated_at TIMESTAMPTZ NOT NULL
        );
        REVOKE ALL ON inventory_item_images FROM ashana_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON inventory_item_images TO ashana_app;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE inventory_item_images")

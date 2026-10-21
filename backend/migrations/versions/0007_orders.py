"""Add guest checkouts, paid mock orders, slots, reservations and outbox."""

from alembic import op

revision = "0007_orders"
down_revision = "0006_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE order_guests (
	id UUID NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (token_hash)
)
    """)
    op.execute("""
CREATE TABLE order_slots (
	id UUID NOT NULL, 
	period_id UUID NOT NULL, 
	starts_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	ends_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	cutoff_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	capacity INTEGER NOT NULL, 
	occupied INTEGER NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	version INTEGER NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_order_slot_capacity CHECK (capacity BETWEEN 1 AND
1000 AND
occupied BETWEEN 0 AND
capacity AND
version > 0), 
	CONSTRAINT ck_order_slot_window CHECK (cutoff_at <= starts_at AND
starts_at < ends_at), 
	FOREIGN KEY(period_id) REFERENCES catalog_periods (id)
)
    """)
    op.execute("""
CREATE INDEX ix_order_slots_period_id
ON order_slots (period_id)
    """)
    op.execute("""
CREATE TABLE checkout_drafts (
	id UUID NOT NULL, 
	guest_id UUID NOT NULL, 
	slot_id UUID NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	total_minor BIGINT NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	version INTEGER NOT NULL, 
	lines JSONB NOT NULL, 
	slot_starts_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	slot_ends_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_order_status CHECK (status IN ('pending_payment','confirmed','preparing','ready',
'completed','cancelled','expired','no_show')), 
	CONSTRAINT ck_order_values CHECK (total_minor >= 0 AND
version > 0), 
	FOREIGN KEY(guest_id) REFERENCES order_guests (id), 
	FOREIGN KEY(slot_id) REFERENCES order_slots (id)
)
    """)
    op.execute("""
CREATE INDEX ix_checkout_drafts_guest_id
ON checkout_drafts (guest_id)
    """)
    op.execute("""
CREATE INDEX ix_checkout_drafts_expires_at
ON checkout_drafts (expires_at)
    """)
    op.execute("""
CREATE TABLE payment_attempts (
	id UUID NOT NULL, 
	checkout_id UUID NOT NULL, 
	mode VARCHAR(10) NOT NULL, 
	outcome VARCHAR(20) NOT NULL, 
	amount_minor BIGINT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_payment_mock CHECK (mode = 'mock' AND
outcome IN ('success','failed','timeout',
'refunded') AND
amount_minor >= 0), 
	FOREIGN KEY(checkout_id) REFERENCES checkout_drafts (id)
)
    """)
    op.execute("""
CREATE TABLE orders (
	id UUID NOT NULL, 
	payment_id UUID NOT NULL, 
	total_minor BIGINT NOT NULL, 
	mode VARCHAR(10) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_order_paid CHECK (total_minor >= 0 AND
mode = 'mock'), 
	FOREIGN KEY(id) REFERENCES checkout_drafts (id), 
	UNIQUE (payment_id), 
	FOREIGN KEY(payment_id) REFERENCES payment_attempts (id)
)
    """)
    op.execute("""
CREATE TABLE order_requests (
	actor_id UUID NOT NULL, 
	operation VARCHAR(30) NOT NULL, 
	key UUID NOT NULL, 
	fingerprint VARCHAR(64) NOT NULL, 
	subject_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (actor_id, operation, key)
)
    """)
    op.execute("""
CREATE TABLE order_events (
	id UUID NOT NULL, 
	subject_id UUID NOT NULL, 
	actor_id UUID, 
	kind VARCHAR(30) NOT NULL, 
	snapshot JSONB NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
)
    """)
    op.execute("""
CREATE INDEX ix_order_events_subject_id
ON order_events (subject_id)
    """)
    op.execute("""
CREATE TABLE inventory_reservations (
	order_id UUID NOT NULL, 
	batch_id UUID NOT NULL, 
	quantity INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	released_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (order_id, batch_id), 
	CONSTRAINT ck_reservation_quantity CHECK (quantity > 0), 
	FOREIGN KEY(batch_id) REFERENCES inventory_batches (id)
)
    """)
    op.execute("""
CREATE TABLE inventory_reservation_events (
	id UUID NOT NULL, 
	order_id UUID NOT NULL, 
	batch_id UUID NOT NULL, 
	action VARCHAR(20) NOT NULL, 
	quantity INTEGER NOT NULL, 
	actor_id UUID, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_reservation_event CHECK (action IN ('reserve','release') AND
quantity > 0), 
	FOREIGN KEY(batch_id) REFERENCES inventory_batches (id)
)
    """)
    op.execute("""
CREATE INDEX ix_inventory_reservation_events_order_id
ON inventory_reservation_events (order_id)
    """)
    op.execute("""
CREATE TABLE notification_outbox (
	id UUID NOT NULL, 
	text TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	attempts INTEGER NOT NULL, 
	lease UUID, 
	lease_until TIMESTAMP WITH TIME ZONE, 
	delivered_at TIMESTAMP WITH TIME ZONE, 
	error_code VARCHAR(30), 
	PRIMARY KEY (id)
)
    """)
    op.execute(
        "REVOKE DELETE ON order_guests, order_slots, checkout_drafts, "
        "inventory_reservations, notification_outbox FROM ashana_app"
    )
    op.execute(
        "REVOKE UPDATE, DELETE ON orders, payment_attempts, order_requests, "
        "order_events, inventory_reservation_events FROM ashana_app"
    )


def downgrade() -> None:
    raise RuntimeError("Откат требует плана сохранения заказов и резервов")

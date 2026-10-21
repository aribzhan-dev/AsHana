from alembic import context
from sqlalchemy import MetaData

from ashana.bootstrap.database import create_database_engine
from ashana.bootstrap.settings import Settings
from ashana.modules.catalog.infrastructure.database import metadata as catalog_metadata
from ashana.modules.identity.infrastructure.database import metadata
from ashana.modules.inventory.infrastructure import reservations  # noqa: F401
from ashana.modules.inventory.infrastructure.database import metadata as inventory_metadata
from ashana.modules.notifications.infrastructure.delivery import metadata as notifications_metadata
from ashana.modules.orders.infrastructure.database import metadata as orders_metadata
from ashana.modules.production.infrastructure.database import metadata as production_metadata

target_metadata = MetaData()
for table in metadata.tables.values():
    table.to_metadata(target_metadata)
for table in inventory_metadata.tables.values():
    if table.name != "identity_users":
        table.to_metadata(target_metadata)

for table in production_metadata.tables.values():
    if table.name not in target_metadata.tables:
        table.to_metadata(target_metadata)

for table in catalog_metadata.tables.values():
    if table.name not in target_metadata.tables:
        table.to_metadata(target_metadata)

for table in orders_metadata.tables.values():
    if table.name not in target_metadata.tables:
        table.to_metadata(target_metadata)

for table in notifications_metadata.tables.values():
    table.to_metadata(target_metadata)

if context.is_offline_mode():
    context.configure(
        dialect_name="postgresql", target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_database_engine(Settings())
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()

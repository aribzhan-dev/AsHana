from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from ashana.bootstrap.settings import Settings

SCHEMA_REVISION = "0020_staff_profile"


def create_database_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        # A lunch rush queues checkouts on one batch row; requests wait for a connection
        # instead of failing (tests/test_load_postgres.py). Default PostgreSQL limit is 100.
        pool_size=10,
        max_overflow=10,
        pool_timeout=10,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
        hide_parameters=True,
    )


def create_side_engine(settings: Settings) -> Engine:
    """Short writes made while a pooled transaction is open (rate limits).

    Taking a second connection from the same pool inside a transaction starves the pool
    under concurrency: every request holds one connection and waits for another.
    """
    return create_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
        hide_parameters=True,
    )


def database_is_ready(engine: Engine) -> bool:
    try:
        with engine.connect() as connection:
            revisions = connection.execute(text("SELECT version_num FROM alembic_version"))
            return set(revisions.scalars()) == {SCHEMA_REVISION}
    except SQLAlchemyError:
        return False

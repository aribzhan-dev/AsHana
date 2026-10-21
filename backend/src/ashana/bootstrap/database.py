from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from ashana.bootstrap.settings import Settings

SCHEMA_REVISION = "0011_receiving"


def create_database_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        pool_timeout=3,
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

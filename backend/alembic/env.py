"""Alembic uses the a separately validated migration connection."""

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import database_url
from app.models import scan, source  # noqa: F401  Register mapped tables.
from app.models.auth import Base


def run_migrations() -> None:
    url = database_url(migration=True)
    if context.is_offline_mode():
        context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = create_engine(
        url,
        hide_parameters=True,
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": 5},
    )
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


try:
    run_migrations()
except (SQLAlchemyError, ValueError):
    raise RuntimeError(
        "Migration failed. Check database availability, permissions, and revision."
    ) from None

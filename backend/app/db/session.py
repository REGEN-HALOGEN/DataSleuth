"""SQLAlchemy engine and transaction factory."""

from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def create_database(url: str, *, hosted: bool = False, worker: bool = False):
    options = (
        dict(
            pool_size=2 if worker else 3,
            max_overflow=0,
            pool_timeout=3,
            connect_args={"connect_timeout": 4},
        )
        if hosted
        else dict(pool_size=5, max_overflow=5)
    )
    engine = create_engine(url, hide_parameters=True, pool_pre_ping=True, **options)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def expected_schema() -> set[str]:
    config_file = Path(__file__).resolve().parents[2] / "alembic.ini"
    if not config_file.is_file():
        config_file = Path("alembic.ini")
    return set(ScriptDirectory.from_config(Config(str(config_file))).get_heads())


def check_schema(connection, heads: set[str]) -> None:
    if (
        not heads
        or set(MigrationContext.configure(connection).get_current_heads()) != heads
    ):
        raise RuntimeError("Database schema revision is incompatible.")

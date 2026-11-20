"""SQLAlchemy engine and transaction factory."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def create_database(url: str):
    engine = create_engine(
        url, hide_parameters=True, pool_pre_ping=True, pool_size=5, max_overflow=5
    )
    return engine, sessionmaker(bind=engine, expire_on_commit=False)

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import Config
from models import Base


engine = create_engine(
    Config.DATABASE_URL,
    future=True,
    pool_pre_ping=True,
    pool_size=Config.DB_POOL_SIZE,
    max_overflow=Config.DB_MAX_OVERFLOW,
    pool_recycle=Config.DB_POOL_RECYCLE_SECONDS,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_database() -> None:
    Base.metadata.create_all(bind=engine)


def drop_database() -> None:
    Base.metadata.drop_all(bind=engine)

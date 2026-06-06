from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from configs.config import settings
from infrastructure.persistence.unit_of_work import UnitOfWork

_engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=5,
    pool_recycle=3600,
    connect_args={"ssl": settings.database_ssl},
)

async_session_factory = async_sessionmaker(
    _engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


def get_uow() -> UnitOfWork:
    return UnitOfWork(async_session_factory)

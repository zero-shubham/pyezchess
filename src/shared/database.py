from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shared.config import settings
from shared.unit_of_work import UnitOfWork


def new_uuid() -> _uuid.UUID:
    return _uuid.uuid4()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass

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

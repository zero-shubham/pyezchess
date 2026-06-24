from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.session.interfaces import SessionRepository
from core.session.schemas import Session
from core.session.models import UserSessionModel


class PostgresSessionRepository(SessionRepository):
    def __init__(self, db: AsyncSession):
        self._db = db

    @staticmethod
    def _to_domain(m: UserSessionModel) -> Session:
        return Session(
            id=m.id,
            user_id=m.user_id,
            token_hash=m.token_hash,
            ip_address=m.ip_address,
            user_agent=m.user_agent,
            expires_at=m.expires_at,
            created_at=m.created_at,
            last_active=m.last_active,
        )

    async def create(self, session: Session) -> Session:
        m = UserSessionModel(
            id=session.id,
            user_id=session.user_id,
            token_hash=session.token_hash,
            ip_address=session.ip_address,
            user_agent=session.user_agent,
            expires_at=session.expires_at,
        )
        self._db.add(m)
        await self._db.flush()
        return self._to_domain(m)

    async def get_by_token_hash(self, token_hash: str) -> Session | None:
        stmt = select(UserSessionModel).where(UserSessionModel.token_hash == token_hash)
        result = await self._db.execute(stmt)
        m = result.scalar_one_or_none()
        return self._to_domain(m) if m else None

    async def get_by_user_id(self, user_id: UUID) -> list[Session]:
        stmt = select(UserSessionModel).where(UserSessionModel.user_id == user_id)
        result = await self._db.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def delete(self, session_id: UUID) -> None:
        stmt = delete(UserSessionModel).where(UserSessionModel.id == session_id)
        await self._db.execute(stmt)
        await self._db.flush()

    async def delete_by_user_id(self, user_id: UUID) -> None:
        stmt = delete(UserSessionModel).where(UserSessionModel.user_id == user_id)
        await self._db.execute(stmt)
        await self._db.flush()

    async def update_last_active(self, session_id: UUID) -> None:
        from datetime import datetime, timezone
        stmt = update(UserSessionModel).where(UserSessionModel.id == session_id).values(last_active=datetime.now(timezone.utc))
        await self._db.execute(stmt)
        await self._db.flush()

    async def delete_expired(self) -> None:
        from datetime import datetime, timezone
        stmt = delete(UserSessionModel).where(UserSessionModel.expires_at < datetime.now(timezone.utc))
        await self._db.execute(stmt)
        await self._db.flush()

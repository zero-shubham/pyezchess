from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from domain.game.model import (
    Event,
    EventRole,
    EventType,
    GameSession,
    GameSessionStatus,
    Level,
    UserProgress,
)
from domain.game.repository import GameRepository
from infrastructure.persistence.postgres.models import (
    GameSessionEventModel,
    GameSessionModel,
    UserProgressModel,
)


class PostgresGameRepository(GameRepository):
    def __init__(self, db: AsyncSession):
        self._db = db

    @staticmethod
    def _serialize_meta(meta: dict | None) -> str | None:
        return json.dumps(meta) if meta else None

    @staticmethod
    def _deserialize_meta(raw: str | None) -> dict | None:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def _session_to_domain(m: GameSessionModel) -> GameSession:
        return GameSession(
            id=m.id,
            user_id=m.user_id,
            level=Level(m.level),
            status=GameSessionStatus(m.status),
            initial_fen=m.initial_fen or "",
            current_fen=m.current_fen or "",
            metadata=PostgresGameRepository._deserialize_meta(m.game_metadata),
            token_usage=m.token_usage or 0,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

    @staticmethod
    def _event_to_domain(m: GameSessionEventModel) -> Event:
        meta = m.event_metadata if isinstance(m.event_metadata, dict) else None
        return Event(
            id=m.id,
            game_session_id=m.game_session_id,
            user_id=m.user_id,
            role=EventRole(m.role),
            event_type=EventType(m.event_type),
            payload=m.payload,
            metadata=meta,
            created_at=m.created_at,
        )

    @staticmethod
    def _progress_to_domain(m: UserProgressModel) -> UserProgress:
        return UserProgress(
            id=m.id,
            user_id=m.user_id,
            level=Level(m.level),
            topic_id=m.topic_id,
            topic_completed=m.topic_completed,
            score=m.score,
            attempts=m.attempts,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

    async def create_session(self, session: GameSession) -> GameSession:
        m = GameSessionModel(
            id=session.id,
            user_id=session.user_id,
            level=session.level.value,
            status=session.status.value,
            initial_fen=session.initial_fen,
            current_fen=session.current_fen,
            game_metadata=self._serialize_meta(session.metadata),
            token_usage=session.token_usage,
        )
        self._db.add(m)
        await self._db.flush()
        return self._session_to_domain(m)

    async def get_session(self, session_id: UUID) -> GameSession | None:
        m = await self._db.get(GameSessionModel, session_id)
        return self._session_to_domain(m) if m else None

    async def get_active_session(self, user_id: UUID) -> GameSession | None:
        stmt = select(GameSessionModel).where(
            GameSessionModel.user_id == user_id,
            GameSessionModel.status == "active",
        ).order_by(GameSessionModel.created_at.desc()).limit(1)
        result = await self._db.execute(stmt)
        m = result.scalar_one_or_none()
        return self._session_to_domain(m) if m else None

    async def update_session(self, session: GameSession) -> GameSession:
        stmt = (
            update(GameSessionModel)
            .where(GameSessionModel.id == session.id)
            .values(
                level=session.level.value,
                status=session.status.value,
                current_fen=session.current_fen,
                game_metadata=self._serialize_meta(session.metadata),
                token_usage=session.token_usage,
            )
            .returning(GameSessionModel)
        )
        result = await self._db.execute(stmt)
        m = result.scalar_one()
        return self._session_to_domain(m)

    async def create_event(self, event: Event) -> Event:
        m = GameSessionEventModel(
            id=event.id,
            game_session_id=event.game_session_id,
            user_id=event.user_id,
            role=event.role.value,
            event_type=event.event_type.value,
            payload=event.payload,
            event_metadata=event.metadata,
        )
        self._db.add(m)
        await self._db.flush()
        return self._event_to_domain(m)

    async def get_events_by_session(self, session_id: UUID, limit: int = 100) -> list[Event]:
        stmt = (
            select(GameSessionEventModel)
            .where(GameSessionEventModel.game_session_id == session_id)
            .order_by(GameSessionEventModel.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return [self._event_to_domain(m) for m in result.scalars().all()]

    async def get_events_by_user(self, user_id: UUID, limit: int = 100) -> list[Event]:
        stmt = (
            select(GameSessionEventModel)
            .where(GameSessionEventModel.user_id == user_id)
            .order_by(GameSessionEventModel.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return [self._event_to_domain(m) for m in result.scalars().all()]

    async def upsert_progress(self, progress: UserProgress) -> UserProgress:
        stmt = select(UserProgressModel).where(
            UserProgressModel.user_id == progress.user_id,
            UserProgressModel.level == progress.level.value,
            UserProgressModel.topic_id == progress.topic_id,
        )
        result = await self._db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.score = progress.score
            existing.topic_completed = progress.topic_completed
            existing.attempts = progress.attempts
            await self._db.flush()
            return self._progress_to_domain(existing)
        else:
            m = UserProgressModel(
                id=progress.id,
                user_id=progress.user_id,
                level=progress.level.value,
                topic_id=progress.topic_id,
                topic_completed=progress.topic_completed,
                score=progress.score,
                attempts=progress.attempts,
            )
            self._db.add(m)
            await self._db.flush()
            return self._progress_to_domain(m)

    async def get_progress(self, user_id: UUID, level: Level, topic_id: str) -> UserProgress | None:
        stmt = select(UserProgressModel).where(
            UserProgressModel.user_id == user_id,
            UserProgressModel.level == level.value,
            UserProgressModel.topic_id == topic_id,
        )
        result = await self._db.execute(stmt)
        m = result.scalar_one_or_none()
        return self._progress_to_domain(m) if m else None

    async def get_all_progress(self, user_id: UUID) -> list[UserProgress]:
        stmt = select(UserProgressModel).where(UserProgressModel.user_id == user_id)
        result = await self._db.execute(stmt)
        return [self._progress_to_domain(m) for m in result.scalars().all()]

    async def get_user_sessions(self, user_id: UUID, limit: int = 50) -> list[GameSession]:
        stmt = (
            select(GameSessionModel)
            .where(GameSessionModel.user_id == user_id)
            .order_by(GameSessionModel.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return [self._session_to_domain(m) for m in result.scalars().all()]

    async def delete_session(self, session_id: UUID) -> None:
        stmt = delete(GameSessionModel).where(GameSessionModel.id == session_id)
        await self._db.execute(stmt)
        await self._db.flush()

    async def increment_token_usage(self, session_id: UUID, tokens: int) -> None:
        stmt = (
            update(GameSessionModel)
            .where(GameSessionModel.id == session_id)
            .values(token_usage=GameSessionModel.token_usage + tokens)
        )
        await self._db.execute(stmt)
        await self._db.flush()

    async def update_current_fen(self, session_id: UUID, current_fen: str) -> None:
        stmt = (
            update(GameSessionModel)
            .where(GameSessionModel.id == session_id)
            .values(current_fen=current_fen)
        )
        await self._db.execute(stmt)
        await self._db.flush()

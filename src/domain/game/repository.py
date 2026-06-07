from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from domain.game.model import Event, GameSession, Level, UserProgress


class GameRepository(ABC):
    @abstractmethod
    async def create_session(self, session: GameSession) -> GameSession: ...

    @abstractmethod
    async def get_session(self, session_id: UUID) -> GameSession | None: ...

    @abstractmethod
    async def get_active_session(self, user_id: UUID) -> GameSession | None: ...

    @abstractmethod
    async def update_session(self, session: GameSession) -> GameSession: ...

    @abstractmethod
    async def create_event(self, event: Event) -> Event: ...

    @abstractmethod
    async def get_events_by_session(self, session_id: UUID, event_types: list[str], limit: int = 100) -> list[Event]: ...

    @abstractmethod
    async def get_events_by_user(self, user_id: UUID, limit: int = 100) -> list[Event]: ...

    @abstractmethod
    async def upsert_progress(self, progress: UserProgress) -> UserProgress: ...

    @abstractmethod
    async def get_progress(self, user_id: UUID, level: Level, topic_id: str) -> UserProgress | None: ...

    @abstractmethod
    async def get_all_progress(self, user_id: UUID) -> list[UserProgress]: ...

    @abstractmethod
    async def get_user_sessions(self, user_id: UUID, limit: int = 50) -> list[GameSession]: ...

    @abstractmethod
    async def delete_session(self, session_id: UUID) -> None: ...

    @abstractmethod
    async def increment_token_usage(self, session_id: UUID, tokens: int) -> None: ...

    @abstractmethod
    async def update_current_fen(self, session_id: UUID, current_fen: str) -> None: ...

    @abstractmethod
    async def update_metadata(self, session_id: UUID, metadata: dict) -> None: ...

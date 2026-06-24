from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from core.session.schemas import Session


class SessionRepository(ABC):
    @abstractmethod
    async def create(self, session: Session) -> Session: ...

    @abstractmethod
    async def get_by_token_hash(self, token_hash: str) -> Session | None: ...

    @abstractmethod
    async def get_by_user_id(self, user_id: UUID) -> list[Session]: ...

    @abstractmethod
    async def delete(self, session_id: UUID) -> None: ...

    @abstractmethod
    async def delete_by_user_id(self, user_id: UUID) -> None: ...

    @abstractmethod
    async def update_last_active(self, session_id: UUID) -> None: ...

    @abstractmethod
    async def delete_expired(self) -> None: ...

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from domain.user.model import User, UserRole


class UserRepository(ABC):
    @abstractmethod
    async def create(self, user: User) -> User: ...

    @abstractmethod
    async def find_by_id(self, user_id: UUID) -> User | None: ...

    @abstractmethod
    async def find_by_email_hash(self, email_hash: str) -> User | None: ...

    @abstractmethod
    async def find_by_username(self, username: str) -> User | None: ...

    @abstractmethod
    async def find_by_role(self, role: UserRole) -> list[User]: ...

    @abstractmethod
    async def exists_by_email_hash(self, email_hash: str) -> bool: ...

    @abstractmethod
    async def exists_by_role(self, role: UserRole) -> bool: ...

    @abstractmethod
    async def update_role(self, user_id: UUID, role: UserRole) -> User | None: ...

    @abstractmethod
    async def delete(self, user_id: UUID) -> None: ...

    @abstractmethod
    async def get_password_hash_by_email_hash(self, email_hash: str) -> str | None: ...

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from domain.user.model import User, UserRole
from domain.user.repository import UserRepository
from infrastructure.persistence.postgres.models import UserModel


class PostgresUserRepository(UserRepository):
    def __init__(self, db: AsyncSession):
        self._db = db

    @staticmethod
    def _to_domain(m: UserModel) -> User:
        return User(
            id=m.id,
            username=m.username,
            email_hash=m.email_hash,
            password_hash=m.password_hash,
            role=UserRole(m.role),
            is_active=m.is_active,
            created_at=m.created_at,
            updated_at=m.updated_at,
        )

    async def create(self, user: User) -> User:
        m = UserModel(
            id=user.id,
            username=user.username,
            email_hash=user.email_hash,
            password_hash=user.password_hash,
            role=user.role.value,
            is_active=user.is_active,
        )
        self._db.add(m)
        await self._db.flush()
        return self._to_domain(m)

    async def find_by_id(self, user_id: UUID) -> User | None:
        m = await self._db.get(UserModel, user_id)
        return self._to_domain(m) if m else None

    async def find_by_email_hash(self, email_hash: str) -> User | None:
        stmt = select(UserModel).where(UserModel.email_hash == email_hash)
        result = await self._db.execute(stmt)
        m = result.scalar_one_or_none()
        return self._to_domain(m) if m else None

    async def find_by_username(self, username: str) -> User | None:
        stmt = select(UserModel).where(UserModel.username == username)
        result = await self._db.execute(stmt)
        m = result.scalar_one_or_none()
        return self._to_domain(m) if m else None

    async def find_by_role(self, role: UserRole) -> list[User]:
        stmt = select(UserModel).where(UserModel.role == role.value)
        result = await self._db.execute(stmt)
        return [self._to_domain(m) for m in result.scalars().all()]

    async def exists_by_email_hash(self, email_hash: str) -> bool:
        stmt = select(UserModel).where(UserModel.email_hash == email_hash)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def exists_by_role(self, role: UserRole) -> bool:
        stmt = select(UserModel).where(UserModel.role == role.value)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def update_role(self, user_id: UUID, role: UserRole) -> User | None:
        stmt = update(UserModel).where(UserModel.id == user_id).values(role=role.value).returning(UserModel)
        result = await self._db.execute(stmt)
        m = result.scalar_one_or_none()
        return self._to_domain(m) if m else None

    async def delete(self, user_id: UUID) -> None:
        stmt = delete(UserModel).where(UserModel.id == user_id)
        await self._db.execute(stmt)
        await self._db.flush()

    async def get_password_hash_by_email_hash(self, email_hash: str) -> str | None:
        stmt = select(UserModel.password_hash).where(UserModel.email_hash == email_hash)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

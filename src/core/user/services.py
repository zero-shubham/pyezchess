from __future__ import annotations

from uuid import UUID

from core.user.interfaces import (
    ErrAdminAlreadyExists,
    ErrInvalidCredentials,
    ErrInvalidInput,
    ErrUserAlreadyExists,
    ErrUserNotFound,
    UserRepository,
    UserServiceInterface,
)
from core.user.models import User, UserRole


class UserService(UserServiceInterface):
    def __init__(self, repo: UserRepository):
        self._repo = repo

    async def create_user(self, username: str, email: str, password: str) -> User:
        if not username or not email or not password:
            raise ErrInvalidInput("username, email, and password are required")
        email_hash = User.hash_email(email)
        if await self._repo.exists_by_email_hash(email_hash):
            raise ErrUserAlreadyExists(f"user with email {email} already exists")
        if await self._repo.find_by_username(username):
            raise ErrUserAlreadyExists(f"user with username {username} already exists")
        user = User(
            username=username,
            email_hash=email_hash,
            password_hash=User.hash_password(password),
            role=UserRole.USER,
        )
        return await self._repo.create(user)

    async def create_admin(self, username: str, email: str, password: str) -> User:
        if await self._repo.exists_by_role(UserRole.ADMIN):
            raise ErrAdminAlreadyExists("admin user already exists")
        if not username or not email or not password:
            raise ErrInvalidInput("username, email, and password are required")
        email_hash = User.hash_email(email)
        if await self._repo.exists_by_email_hash(email_hash):
            raise ErrUserAlreadyExists(f"user with email {email} already exists")
        user = User(
            username=username,
            email_hash=email_hash,
            password_hash=User.hash_password(password),
            role=UserRole.ADMIN,
        )
        return await self._repo.create(user)

    async def authenticate(self, email: str, password: str) -> User:
        email_hash = User.hash_email(email)
        user = await self._repo.find_by_email_hash(email_hash)
        if user is None:
            raise ErrInvalidCredentials("invalid email or password")
        if not user.check_password(password):
            raise ErrInvalidCredentials("invalid email or password")
        return user

    async def find_by_id(self, user_id: UUID) -> User | None:
        return await self._repo.find_by_id(user_id)

    async def find_by_username(self, username: str) -> User | None:
        return await self._repo.find_by_username(username)

    async def list_users(self) -> list[User]:
        return await self._repo.find_by_role(UserRole.USER)

    async def list_admins(self) -> list[User]:
        return await self._repo.find_by_role(UserRole.ADMIN)

    async def update_role(self, user_id: UUID, role: UserRole) -> User:
        user = await self._repo.update_role(user_id, role)
        if user is None:
            raise ErrUserNotFound(f"user {user_id} not found")
        return user

    async def delete_user(self, user_id: UUID) -> None:
        user = await self._repo.find_by_id(user_id)
        if user is None:
            raise ErrUserNotFound(f"user {user_id} not found")
        await self._repo.delete(user_id)

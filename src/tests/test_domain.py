from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest
from unittest.mock import AsyncMock, MagicMock

from domain.user.model import User, UserRole
from domain.user.service import UserService
from domain.user.repository import UserRepository


class MockUserRepository(UserRepository):
    def __init__(self):
        self._users: dict[UUID, User] = {}

    async def create(self, user: User) -> User:
        self._users[user.id] = user
        return user

    async def find_by_id(self, user_id: UUID) -> User | None:
        return self._users.get(user_id)

    async def find_by_email_hash(self, email_hash: str) -> User | None:
        for u in self._users.values():
            if u.email_hash == email_hash:
                return u
        return None

    async def find_by_username(self, username: str) -> User | None:
        for u in self._users.values():
            if u.username == username:
                return u
        return None

    async def find_by_role(self, role: UserRole) -> list[User]:
        return [u for u in self._users.values() if u.role == role]

    async def exists_by_email_hash(self, email_hash: str) -> bool:
        return await self.find_by_email_hash(email_hash) is not None

    async def exists_by_role(self, role: UserRole) -> bool:
        for u in self._users.values():
            if u.role == role:
                return True
        return False

    async def update_role(self, user_id: UUID, role: UserRole) -> User | None:
        u = self._users.get(user_id)
        if u:
            u.role = role
        return u

    async def delete(self, user_id: UUID) -> None:
        self._users.pop(user_id, None)

    async def get_password_hash_by_email_hash(self, email_hash: str) -> str | None:
        u = await self.find_by_email_hash(email_hash)
        return u.password_hash if u else None


@pytest.fixture
def repo():
    return MockUserRepository()


@pytest.fixture
def svc(repo):
    return UserService(repo)


@pytest.mark.asyncio
async def test_create_user(svc, repo):
    user = await svc.create_user("testuser", "test@example.com", "password123")
    assert user.username == "testuser"
    assert user.role == UserRole.USER
    assert user.check_password("password123")


@pytest.mark.asyncio
async def test_create_user_duplicate_email(svc, repo):
    await svc.create_user("user1", "dup@example.com", "pass1")
    with pytest.raises(Exception):
        await svc.create_user("user2", "dup@example.com", "pass2")


@pytest.mark.asyncio
async def test_create_admin(svc, repo):
    admin = await svc.create_admin("admin", "admin@example.com", "adminpass")
    assert admin.role == UserRole.ADMIN


@pytest.mark.asyncio
async def test_authenticate(svc, repo):
    await svc.create_user("authuser", "auth@example.com", "secret123")
    user = await svc.authenticate("auth@example.com", "secret123")
    assert user.username == "authuser"


@pytest.mark.asyncio
async def test_authenticate_bad_password(svc, repo):
    await svc.create_user("baduser", "bad@example.com", "correct")
    with pytest.raises(Exception):
        await svc.authenticate("bad@example.com", "wrong")


@pytest.mark.asyncio
async def test_create_admin_duplicate(svc, repo):
    await svc.create_admin("admin1", "a1@example.com", "pass")
    with pytest.raises(Exception):
        await svc.create_admin("admin2", "a2@example.com", "pass2")


@pytest.mark.asyncio
async def test_email_hashing():
    h1 = User.hash_email("Test@Example.com")
    h2 = User.hash_email("test@example.com")
    assert h1 == h2
    assert len(h1) == 64


@pytest.mark.asyncio
async def test_password_hashing():
    pw = "mysecret"
    hashed = User.hash_password(pw)
    assert len(hashed) > 0
    u = User(username="t", email_hash="h", password_hash=hashed)
    assert u.check_password(pw)
    assert not u.check_password("wrong")


def test_ws_message_serialization():
    from interfaces.message import WSMessage, WSMessageType, WSMessageSubtype
    msg = WSMessage(
        type=WSMessageType.GAME,
        subtype=WSMessageSubtype.MOVE,
        payload={"move": "e2e4"},
    )
    d = msg.model_dump(mode="json")
    assert d["type"] == "GAME"
    assert d["subtype"] == "move"
    assert d["payload"]["move"] == "e2e4"

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

import bcrypt


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


@dataclass
class User:
    id: UUID = field(default_factory=uuid4)
    username: str = ""
    email_hash: str = ""
    password_hash: str = ""
    role: UserRole = UserRole.USER
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def check_password(self, password: str) -> bool:
        return bcrypt.checkpw(password.encode(), self.password_hash.encode())

    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    @staticmethod
    def hash_email(email: str) -> str:
        import hashlib
        return hashlib.sha256(email.strip().lower().encode()).hexdigest()

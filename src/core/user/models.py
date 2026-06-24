from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4
from typing import TYPE_CHECKING

import bcrypt

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import UUID as SA_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database import Base, new_uuid, utcnow

if TYPE_CHECKING:
    from core.session.models import UserSessionModel
    from core.game.models import GameSessionModel


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


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), primary_key=True, default=new_uuid)
    username: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    sessions: Mapped[list["UserSessionModel"]] = relationship(back_populates="user", lazy="selectin")
    game_sessions: Mapped[list["GameSessionModel"]] = relationship(back_populates="user", lazy="selectin")

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as SA_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database import Base, new_uuid, utcnow

if TYPE_CHECKING:
    from core.user.models import UserModel


@dataclass
class Session:
    id: UUID = field(default_factory=uuid4)
    user_id: UUID | None = None
    token_hash: str = ""
    ip_address: str = ""
    user_agent: str = ""
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at


def new_session(user_id: UUID, token_hash: str, ip: str = "", ua: str = "", ttl_seconds: int = 86400) -> Session:
    now = datetime.now(timezone.utc)
    return Session(
        user_id=user_id,
        token_hash=token_hash,
        ip_address=ip,
        user_agent=ua,
        expires_at=datetime.fromtimestamp(now.timestamp() + ttl_seconds, tz=timezone.utc),
        created_at=now,
        last_active=now,
    )


class UserSessionModel(Base):
    __tablename__ = "user_sessions"

    id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    ip_address: Mapped[str] = mapped_column(String(45), default="")
    user_agent: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_active: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["UserModel"] = relationship(back_populates="sessions")

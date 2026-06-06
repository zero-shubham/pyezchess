from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


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

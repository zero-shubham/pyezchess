
import asyncio
import time
from uuid import UUID
from typing import Any
from dataclasses import dataclass, field

from shared.message import WSMessage, WSMessageType, WSMessageSubtype


@dataclass
class SessionEntry:
    session_id: UUID
    user_id: UUID
    ws: Any
    level: int
    initial_fen: str
    current_fen: str
    last_ping: float = field(default_factory=time.monotonic)


class SessionManager:
    _instance: SessionManager | None = None

    def __new__(cls) -> SessionManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_lock"):
            return
        self._lock = asyncio.Lock()
        self._sessions: dict[UUID, SessionEntry] = {}
        self._ping_task: asyncio.Task | None = None

    async def _monitor_pings(self):
        while True:
            await asyncio.sleep(30)
            async with self._lock:
                now = time.monotonic()
                stale = [sid for sid, entry in self._sessions.items()
                         if now - entry.last_ping > 180]
                for sid in stale:
                    del self._sessions[sid]

    def start_ping_monitor(self):
        self._ping_task = asyncio.create_task(self._monitor_pings())

    async def create(self, entry: SessionEntry) -> None:
        async with self._lock:
            old = None
            for sid, e in self._sessions.items():
                if e.user_id == entry.user_id:
                    old = (sid, e)
                    break
            if old:
                sid, old_entry = old
                try:
                    await old_entry.ws.send_json(WSMessage(
                        type=WSMessageType.NOTIFICATION,
                        subtype=WSMessageSubtype.ERROR,
                        payload="Connection closed: new session started",
                    ).model_dump(mode="json"))
                except Exception:
                    pass
                try:
                    await old_entry.ws.close()
                except Exception:
                    pass
                del self._sessions[sid]

            self._sessions[entry.session_id] = entry

    async def get(self, session_id: UUID) -> SessionEntry | None:
        async with self._lock:
            return self._sessions.get(session_id)

    async def get_by_user(self, user_id: UUID) -> SessionEntry | None:
        async with self._lock:
            for entry in self._sessions.values():
                if entry.user_id == user_id:
                    return entry
            return None

    async def replace(self, entry: SessionEntry):
        async with self._lock:
            existing = self._sessions.get(entry.session_id)
            if existing:
                try:
                    await existing.ws.close()
                except Exception:
                    pass
            self._sessions[entry.session_id] = entry

    async def remove(self, session_id: UUID):
        async with self._lock:
            self._sessions.pop(session_id, None)

    async def update_ping(self, session_id: UUID):
        async with self._lock:
            entry = self._sessions.get(session_id)
            if entry:
                entry.last_ping = time.monotonic()

    async def send(self, session_id: UUID, message: WSMessage):
        async with self._lock:
            entry = self._sessions.get(session_id)
        if entry:
            try:
                await entry.ws.send_json(message.model_dump(mode="json"))
            except Exception:
                pass

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel


class WSMessageType(StrEnum):
    GAME = "GAME"
    NOTIFICATION = "NOTIFICATION"
    PING = "PING"


class WSMessageSubtype(StrEnum):
    MOVE = "move"
    HINT = "hint"
    EXPLAIN = "explain"
    MOVE_RESULT = "move_result"
    BOARD = "board"
    START_GAME = "start_game"
    ERROR = "error"
    INFO = "info"
    SUCCESS = "success"
    WARN = "warn"


@dataclass
class SessionContext:
    game_session_id: str = ""
    user_id: str = ""
    username: str = ""
    level: int = 1
    fen: str = ""
    white: str = "student"


class WSMessage(BaseModel):
    type: WSMessageType
    subtype: WSMessageSubtype | None = None
    payload: Any | None = None
    client_id: str | None = None
    timestamp: float | None = None


@runtime_checkable
class MessageSender(Protocol):

    async def send_message(self, msg: WSMessage) -> None: ...

    async def send_notification(
        self, subtype: WSMessageSubtype, payload: Any = None) -> None: ...
    async def send_move(self, move: str, fen: str = "",
                        message: str = "") -> None: ...

    async def send_score(self, grade: str, delta: int, reason: str) -> None: ...

    async def send_start_game(self, level: int, fen: str, white: str = "student") -> None: ...




from core.game.board import EzBoard
from core.game.schemas import (
    Event,
    EventRole,
    EventType,
    GameMetadata,
    GameSession,
    GameSessionStatus,
    Level,
    UserProgress,
)
from core.game.interfaces import GameRepository


def __getattr__(name: str):
    if name == "ToolProvider":
        from core.game.tools import ToolProvider
        return ToolProvider
    if name == "GameService":
        from core.game.services import GameService
        return GameService
    if name == "SessionEntry":
        from core.game.services import SessionEntry
        return SessionEntry
    if name == "SessionManager":
        from core.game.services import SessionManager
        return SessionManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "EzBoard",
    "Event",
    "EventRole",
    "EventType",
    "GameMetadata",
    "GameSession",
    "GameSessionStatus",
    "Level",
    "UserProgress",
    "GameRepository",
]

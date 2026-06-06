from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum, StrEnum
from uuid import UUID, uuid4


class Level(IntEnum):
    FUNDAMENTALS = 1
    TACTICS = 2
    OPENING = 3
    STRATEGY = 4


class GameSessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class EventRole(StrEnum):
    STUDENT = "student"
    INSTRUCTOR = "instructor"


class EventType(StrEnum):
    MOVE = "move"
    HINT = "hint"
    EXPLAIN = "explain"
    MOVE_RESULT = "move_result"
    START_GAME = "start_game"


@dataclass
class Event:
    id: UUID = field(default_factory=uuid4)
    game_session_id: UUID | None = None
    user_id: UUID | None = None
    role: EventRole = EventRole.STUDENT
    event_type: EventType = EventType.START_GAME
    payload: str = ""
    metadata: dict | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class GameSession:
    id: UUID = field(default_factory=uuid4)
    user_id: UUID | None = None
    level: Level = Level.FUNDAMENTALS
    status: GameSessionStatus = GameSessionStatus.ACTIVE
    initial_fen: str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    current_fen: str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    metadata: dict | None = None
    token_usage: int = 0
    user_token_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class UserProgress:
    id: UUID = field(default_factory=uuid4)
    user_id: UUID | None = None
    level: Level = Level.FUNDAMENTALS
    topic_id: str = ""
    topic_completed: bool = False
    score: int = 0
    attempts: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class GameMetadata:
    current_topic_id: str | None = None
    topic_started: bool = False
    move_count: int = 0
    last_move: str | None = None
    last_move_result: str | None = None
    white: str = "student"

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum, StrEnum
from uuid import UUID, uuid4
from typing import TYPE_CHECKING

import chess
from chess import Board, Move
from collections.abc import Callable

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as SA_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.database import Base, new_uuid, utcnow

if TYPE_CHECKING:
    from core.user.models import UserModel

MOVE_SIDE = str

# ── Enums ────────────────────────────────────────────────────────────────────


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
    QUERY = "query"


# ── Domain Dataclass Models ──────────────────────────────────────────────────


@dataclass
class Event:
    id: UUID = field(default_factory=uuid4)
    game_session_id: UUID | None = None
    user_id: UUID | None = None
    role: EventRole = EventRole.STUDENT
    event_type: EventType = EventType.START_GAME
    payload: str = ""
    metadata: dict | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class GameSession:
    id: UUID = field(default_factory=uuid4)
    user_id: UUID | None = None
    level: Level = Level.FUNDAMENTALS
    status: GameSessionStatus = GameSessionStatus.ACTIVE
    initial_fen: str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    current_fen: str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    metadata: dict | None = None
    token_usage: dict[str, int] = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})
    user_token_id: UUID | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class UserProgress:
    id: UUID = field(default_factory=uuid4)
    user_id: UUID | None = None
    level: Level = Level.FUNDAMENTALS
    topic_id: str = ""
    topic_completed: bool = False
    score: int = 0
    attempts: int = 0
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class GameMetadata:
    current_topic_id: str | None = None
    topic_started: bool = False
    move_count: int = 0
    last_move: str | None = None
    last_move_result: str | None = None
    white: str = "student"


# ── ORM Table Models ─────────────────────────────────────────────────────────


class GameSessionModel(Base):
    __tablename__ = "game_sessions"

    id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[UUID | None] = mapped_column(SA_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    initial_fen: Mapped[str] = mapped_column(Text, nullable=False)
    current_fen: Mapped[str] = mapped_column(Text, nullable=False)
    game_metadata: Mapped[str | None] = mapped_column("metadata", Text, nullable=True)
    token_usage: Mapped[dict] = mapped_column(JSONB, default=lambda: {"input_tokens": 0, "output_tokens": 0})
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    events: Mapped[list["GameSessionEventModel"]] = relationship(back_populates="game_session", lazy="selectin", order_by="GameSessionEventModel.created_at")
    user: Mapped["UserModel | None"] = relationship(back_populates="game_sessions")


class GameSessionEventModel(Base):
    __tablename__ = "game_session_events"

    id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), primary_key=True, default=new_uuid)
    game_session_id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[UUID | None] = mapped_column(SA_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="student")
    event_type: Mapped[str] = mapped_column(String(30), nullable=False, default="start_game")
    payload: Mapped[str] = mapped_column(Text, default="")
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    game_session: Mapped[GameSessionModel] = relationship(back_populates="events")


class UserProgressModel(Base):
    __tablename__ = "user_progress"

    id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), primary_key=True, default=new_uuid)
    user_id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_id: Mapped[str] = mapped_column(String(50), nullable=False)
    topic_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "level", "topic_id", name="uq_user_level_topic"),
    )


# ── Board ────────────────────────────────────────────────────────────────────

logger = __import__("logging").getLogger(__name__)


class EzBoard(Board):

    def __init__(self, fen: str = chess.STARTING_FEN, chess960: bool = False) -> None:
        super().__init__(fen, chess960=chess960)
        self.white_captured: list[str] = []
        self.black_captured: list[str] = []
        self._capture_records: list[bool | None] = []
        self.on_captured: Callable[[], None] | None = None

    @property
    def captured(self) -> dict[str, list[str]]:
        return {
            "white": list(self.white_captured),
            "black": list(self.black_captured),
        }

    def set_captured(self, data: dict[str, list[str]]) -> None:
        self.white_captured = list(data.get("white", []))
        self.black_captured = list(data.get("black", []))

    def reset(self) -> None:
        super().reset()
        self.white_captured = []
        self.black_captured = []
        self._capture_records = []

    def push(self, move: Move) -> None:
        captured = False
        if self.is_capture(move):
            captured_piece = None
            if self.is_en_passant(move):
                captured_piece = chess.Piece(chess.PAWN, not self.turn)
            else:
                captured_piece = self.piece_at(move.to_square)

            if captured_piece:
                symbol = captured_piece.symbol()
                if self.turn == chess.WHITE:
                    logger.info("appending %r to white_captured (previous: %s)", symbol, self.white_captured)
                    self.white_captured.append(symbol)
                else:
                    logger.info("appending %r to black_captured (previous: %s)", symbol, self.black_captured)
                    self.black_captured.append(symbol)
                captured = True

                if self.on_captured:
                    self.on_captured()

        self._capture_records.append(self.turn == chess.WHITE if captured else None)
        return super().push(move)

    def get_legal_moves_san(self) -> list[str]:
        san_board = Board(self.fen())
        return [san_board.san(m) for m in self.legal_moves]

    def pop(self) -> Move:
        if self._capture_records:
            record = self._capture_records.pop()
            if record is not None:
                (self.white_captured if record else self.black_captured).pop()
        return super().pop()

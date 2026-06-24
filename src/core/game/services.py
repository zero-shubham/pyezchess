from __future__ import annotations

import asyncio
import chess
import json
import logging
import time
from collections.abc import Callable
from uuid import UUID
from typing import Any
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.game.schemas import EzBoard, GameMetadata, GameSession, Level, UserProgress, Event, EventRole, EventType
from core.game.repository import PostgresGameRepository
from core.agent.models import MovePlayedResult
from shared.message import MessageSender, WSMessage, WSMessageType, WSMessageSubtype
from shared.unit_of_work import UnitOfWork

logger = logging.getLogger(__name__)


# ── Session Manager ──────────────────────────────────────────────────────────


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
                stale = [sid for sid, entry in self._sessions.items() if now - entry.last_ping > 180]
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


# ── Game Service ─────────────────────────────────────────────────────────────


class GameService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
        self._session_manager = SessionManager()
        self._instructor: Any = None
        self._msg_manager: MessageSender | None = None
        self.board: EzBoard | None = None
        self.white: str = "student"

    def set_instructor(self, instructor: Any) -> None:
        self._instructor = instructor

    def get_fen(self) -> str:
        if self.board is None:
            return EzBoard().fen()
        return self.board.fen()

    def _make_captured_callback(self, game_session_id: UUID) -> Callable[[], None]:
        def _sync_blocking_wrapper(loop):
            future = asyncio.run_coroutine_threadsafe(
                self._do_persist_captured(game_session_id), loop
            )
            future.result()

        def _on_captured() -> None:
            loop = asyncio.get_running_loop()
            asyncio.ensure_future(
                asyncio.to_thread(_sync_blocking_wrapper, loop)
            )

        return _on_captured

    async def _do_persist_captured(self, game_session_id: UUID) -> None:
        if not self.board:
            return
        captured_state = self.board.captured

        try:
            if self._msg_manager:
                await self._msg_manager.send_message(WSMessage(
                    type=WSMessageType.GAME,
                    subtype=WSMessageSubtype.CAPTURED,
                    payload=captured_state,
                ))

            async with UnitOfWork(self._session_factory) as uow:
                repo = PostgresGameRepository(uow.session)
                session = await repo.get_session(game_session_id)
                if session:
                    metadata = session.metadata or {}
                    metadata["captured"] = captured_state
                    await repo.update_metadata(game_session_id, metadata)
                    await uow.commit()
        except Exception:
            logger.exception(
                "Failed to persist captured state for session %s", game_session_id)

    def set_msg_manager(self, msg_manager: MessageSender) -> None:
        self._msg_manager = msg_manager

    async def persist_fen(self, game_session_id: UUID, fen: str) -> None:
        try:
            async with UnitOfWork(self._session_factory) as uow:
                repo = PostgresGameRepository(uow.session)
                await repo.update_current_fen(game_session_id, fen)
                await uow.commit()
        except Exception:
            logger.exception(
                "Failed to persist current_fen for session %s", game_session_id)

    @property
    def instructor(self) -> Any | None:
        return self._instructor

    async def begin(self, user_id: str, username: str, level: int) -> Any:
        if not self._instructor:
            raise RuntimeError("No instructor configured")
        if not self._msg_manager:
            raise RuntimeError("No message manager configured")
        result = await self._instructor.begin_game(self, user_id, username, level)

        payload_fen = result.fen
        self.board = EzBoard(payload_fen)
        self.board.set_captured(result.captured or {"white": [], "black": []})
        self.board.on_captured = self._make_captured_callback(
            UUID(result.game_session_id))

        await self._msg_manager.send_message(WSMessage(
            type=WSMessageType.GAME,
            subtype=WSMessageSubtype.START_GAME,
            payload={
                "level": level,
                "fen": payload_fen,
                "white": result.white,
                "captured": self.board.captured,
                "game_session_id": result.game_session_id
            },
        ))

        await self._msg_manager.send_message(WSMessage(
            type=WSMessageType.GAME,
            subtype=WSMessageSubtype.EXPLAIN,
            payload={"message": result.explanation},
        ))
        await self.add_event(Event(
            game_session_id=UUID(result.game_session_id),
            user_id=UUID(user_id),
            role=EventRole.INSTRUCTOR,
            event_type=EventType.EXPLAIN,
            metadata={"message": result.explanation},
        ))

        if result.instructor_move:
            await self._msg_manager.send_message(WSMessage(
                type=WSMessageType.GAME,
                subtype=WSMessageSubtype.MOVE,
                payload={"move": result.instructor_move, "fen": payload_fen},
            ))
            await self.add_event(Event(
                game_session_id=UUID(result.game_session_id),
                user_id=UUID(user_id),
                role=EventRole.INSTRUCTOR,
                event_type=EventType.MOVE,
                metadata={"move": result.instructor_move, "fen": payload_fen},
            ))

        self.white = result.white
        return result

    async def handle_move(self, user_id: str, username: str, level: int,
                          move: str, fen: str, game_session_id: str) -> Any:
        if not self._instructor:
            raise RuntimeError("No instructor configured")

        if not self.board:
            raise RuntimeError("handle_move called before begin")

        try:
            user_move = self.board.parse_san(move)
            if user_move not in self.board.legal_moves:
                return MovePlayedResult(valid=False, explanation="Invalid move: not a legal move")
        except (ValueError, chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError) as e:
            logger.warning("Invalid user move %r on board %s: %s",
                           move, self.board.fen(), e)
            return MovePlayedResult(valid=False, explanation=f"Invalid move: {e}")

        legal_moves = self.board.get_legal_moves_san()

        result = await self._instructor.handle_move(
            game_svc=self,
            move=move,
            fen=self.board.fen(),
            game_session_id=game_session_id,
            user_id=user_id,
            username=username,
            level=level,
            legal_moves=legal_moves,
            white=self.white,
        )

        if result.commentary and self._msg_manager:
            await self._msg_manager.send_message(WSMessage(
                type=WSMessageType.GAME,
                subtype=WSMessageSubtype.EXPLAIN,
                payload={"message": result.commentary, "move": move},
            ))
            await self.add_event(Event(
                game_session_id=UUID(game_session_id),
                user_id=UUID(user_id),
                role=EventRole.INSTRUCTOR,
                event_type=EventType.EXPLAIN,
                metadata={"message": result.commentary, "move": move},
            ))

        instructor_move = result.move
        if instructor_move:
            try:
                move_obj = self.board.parse_san(instructor_move)
                if move_obj in self.board.legal_moves:
                    self.board.push(move_obj)
                    await self.persist_fen(UUID(game_session_id), self.board.fen())
                    result.fen = self.board.fen()
            except (ValueError, chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                logger.exception(
                    "Instructor move %r failed SAN parse after workflow validation", instructor_move)

        return result

    async def handle_query(self, user_id: str, username: str, level: int,
                           query: str, fen: str, game_session_id: str) -> Any:
        if not self._instructor:
            raise RuntimeError("No instructor configured")

        result = await self._instructor.handle_query(
            game_svc=self,
            query=query,
            game_session_id=game_session_id,
            user_id=user_id,
            username=username,
            level=level,
            fen=self.board.fen() if self.board else fen,
            white=self.white,
        )
        return result

    async def start_new_session(self, session: GameSession) -> GameSession:
        async with UnitOfWork(self._session_factory) as uow:
            repo = PostgresGameRepository(uow.session)
            created = await repo.create_session(session)
            await uow.commit()
        try:
            await self.add_event(Event(
                game_session_id=created.id,
                user_id=created.user_id,
                role=EventRole.INSTRUCTOR,
                event_type=EventType.START_GAME,
                metadata={"fen": created.initial_fen, "white": created.metadata.get(
                    "white", "student") if created.metadata else "student"},
            ))
        except Exception:
            logger.exception("failed to record start_game event")
        return created

    async def get_session(self, session_id: UUID) -> GameSession | None:
        async with UnitOfWork(self._session_factory) as uow:
            repo = PostgresGameRepository(uow.session)
            return await repo.get_session(session_id)

    async def update_session(self, session: GameSession) -> GameSession:
        async with UnitOfWork(self._session_factory) as uow:
            repo = PostgresGameRepository(uow.session)
            result = await repo.update_session(session)
            await uow.commit()
            return result

    async def get_active_session(self, user_id: UUID) -> GameSession | None:
        async with UnitOfWork(self._session_factory) as uow:
            repo = PostgresGameRepository(uow.session)
            return await repo.get_active_session(user_id)

    async def add_event(self, event) -> Event:
        async with UnitOfWork(self._session_factory) as uow:
            repo = PostgresGameRepository(uow.session)
            result = await repo.create_event(event)
            await uow.commit()
            return result

    async def get_events(self, session_id: UUID, event_types: list[str], limit: int = 100) -> list[Event]:
        async with UnitOfWork(self._session_factory) as uow:
            repo = PostgresGameRepository(uow.session)
            return await repo.get_events_by_session(session_id, event_types, limit)

    async def upsert_progress(self, progress: UserProgress) -> UserProgress:
        if not progress.user_id:
            raise RuntimeError("user_id missing")

        async with UnitOfWork(self._session_factory) as uow:
            repo = PostgresGameRepository(uow.session)
            current = await repo.get_progress(progress.user_id, progress.level, progress.topic_id)
            if current:
                current.score = progress.score
                current.topic_completed = progress.topic_completed or current.topic_completed
                current.attempts = progress.attempts
                result = await repo.upsert_progress(current)
            else:
                result = await repo.upsert_progress(progress)
            await uow.commit()
            return result

    async def get_progress(self, user_id: UUID, level: Level, topic_id: str) -> UserProgress | None:
        async with UnitOfWork(self._session_factory) as uow:
            repo = PostgresGameRepository(uow.session)
            return await repo.get_progress(user_id, level, topic_id)

    async def get_all_progress(self, user_id: UUID) -> list[UserProgress]:
        async with UnitOfWork(self._session_factory) as uow:
            repo = PostgresGameRepository(uow.session)
            return await repo.get_all_progress(user_id)

    async def get_user_sessions(self, user_id: UUID, limit: int = 50) -> list[GameSession]:
        async with UnitOfWork(self._session_factory) as uow:
            repo = PostgresGameRepository(uow.session)
            return await repo.get_user_sessions(user_id, limit)

    async def increment_token_usage(self, session_id: UUID, input_tokens: int, output_tokens: int) -> None:
        async with UnitOfWork(self._session_factory) as uow:
            repo = PostgresGameRepository(uow.session)
            await repo.increment_token_usage(session_id, input_tokens, output_tokens)
            await uow.commit()

    async def register_session(self, entry: SessionEntry) -> None:
        await self._session_manager.create(entry)

    async def remove_session(self, session_id: UUID) -> None:
        await self._session_manager.remove(session_id)

    async def update_ping(self, session_id: UUID) -> None:
        await self._session_manager.update_ping(session_id)

    @staticmethod
    def marshal_metadata(data: GameMetadata | None) -> str | None:
        if data is None:
            return None
        return json.dumps(data.__dict__)

    @staticmethod
    def unmarshal_metadata(raw: str | None) -> GameMetadata:
        if raw is None:
            return GameMetadata()
        try:
            d = json.loads(raw)
            return GameMetadata(**d)
        except (json.JSONDecodeError, TypeError):
            return GameMetadata()

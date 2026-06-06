from __future__ import annotations

import chess
import json
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from domain.game.model import GameMetadata, GameSession, Level, UserProgress, Event, EventRole, EventType
from domain.game.session_manager import SessionEntry, SessionManager
from domain.instructor.interface import Instructor
from domain.instructor.model import ExplainResult, MovePlayedResult, MOVE_SIDE
from infrastructure.persistence.postgres.game_repository import PostgresGameRepository
from infrastructure.persistence.unit_of_work import UnitOfWork
from protocol.message import MessageSender, WSMessage, WSMessageType, WSMessageSubtype

logger = logging.getLogger(__name__)


class GameService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
        self._session_manager = SessionManager()
        self._instructor: Instructor | None = None
        self._msg_manager: MessageSender | None = None
        self.board: chess.Board | None = None
        self.white: MOVE_SIDE = "student"

    def set_instructor(self, instructor: Instructor) -> None:
        self._instructor = instructor

    def get_fen(self) -> str:
        if self.board is None:
            return chess.Board().fen()
        return self.board.fen()

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
    def instructor(self) -> Instructor | None:
        return self._instructor

    async def begin(self, user_id: str, username: str, level: int) -> ExplainResult:
        if not self._instructor:
            raise RuntimeError("No instructor configured")
        if not self._msg_manager:
            raise RuntimeError("No message manager configured")
        result = await self._instructor.begin_game(self, user_id, username, level)

        payload_fen = result.fen
        self.board = chess.Board(payload_fen)

        await self._msg_manager.send_message(WSMessage(
            type=WSMessageType.GAME,
            subtype=WSMessageSubtype.START_GAME,
            payload={"level": level, "fen": payload_fen,
                     "white": result.white},
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
                          move: str, fen: str, game_session_id: str) -> MovePlayedResult:
        if not self._instructor:
            raise RuntimeError("No instructor configured")

        if not self.board:
            self.board = chess.Board(fen)

        try:
            user_move = self.board.parse_san(move)
            if user_move not in self.board.legal_moves:
                return MovePlayedResult(valid=False, explanation="Invalid move: not a legal move")
        except (ValueError, chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError) as e:
            logger.warning("Invalid user move %r on board %s: %s",
                           move, self.board.fen(), e)
            return MovePlayedResult(valid=False, explanation=f"Invalid move: {e}")

        legal_moves = [self.board.san(m) for m in self.board.legal_moves]

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

    async def get_events(self, session_id: UUID, limit: int = 100) -> list[Event]:
        async with UnitOfWork(self._session_factory) as uow:
            repo = PostgresGameRepository(uow.session)
            return await repo.get_events_by_session(session_id, limit)

    async def upsert_progress(self, progress: UserProgress) -> UserProgress:
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

    async def increment_token_usage(self, session_id: UUID, tokens: int) -> None:
        async with UnitOfWork(self._session_factory) as uow:
            repo = PostgresGameRepository(uow.session)
            await repo.increment_token_usage(session_id, tokens)
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

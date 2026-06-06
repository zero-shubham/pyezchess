from __future__ import annotations

import chess
import logging
from dataclasses import dataclass, field
from typing import Literal, Protocol
from uuid import UUID

from langgraph.graph import StateGraph, END

from domain.game.model import GameSession, GameSessionStatus, Level
from domain.game.service import GameService, UserProgress
from domain.instructor.model import LLMClient, NextMoveOutput

logger = logging.getLogger(__name__)

INSTRUCTOR_OPENING_PROMPT = """You are a chess instructor deciding the opening move to play as the opposing side.

Current FEN (board state): {fen}

Legal moves available: {legal_moves}

Choose a strong, principled opening move — control the center, develop pieces, and set a solid foundation for the game."""


@dataclass
class ProgressState:
    user_id: str = ""
    username: str = ""
    level: int = 1
    fen: str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
    game_session_id: str = ""
    has_active_session: bool = False
    needs_game: bool = False
    greeting: str = ""
    messages: list = field(default_factory=list)
    white: Literal["student", "instructor"] = "student"
    instructor_move: str = ""
    instructor_move_fen: str = ""


class GameSvc(Protocol):
    async def get_active_session(self, user_id: UUID) -> GameSession | None:
        ...

    async def start_new_session(self, session: GameSession) -> GameSession:
        ...

    async def get_all_progress(self, user_id: UUID) -> list[UserProgress]:
        ...

    async def get_user_sessions(self, user_id: UUID, limit: int = 50) -> list[GameSession]:
        ...


def _decide_white(past_session_count: int) -> str:
    if past_session_count % 2 == 0:
        return "student"
    return "instructor"


class UserProgressWorkflow:

    def __init__(self, game_service: GameSvc, llm: LLMClient | None = None) -> None:
        self._game_svc = game_service
        self._llm = llm

    async def check_active_session(self, state: ProgressState) -> dict:
        game_service = self._game_svc
        if game_service is None:
            return {"has_active_session": False, "needs_game": True}

        try:
            session = await game_service.get_active_session(UUID(state.user_id))
        except Exception:
            logger.exception(
                "failed to query active session for user %s", state.user_id)
            return {"has_active_session": False, "needs_game": True}

        if session is not None and session.status == GameSessionStatus.ACTIVE:
            white = "student"
            if session.metadata and "white" in session.metadata:
                white = session.metadata["white"]
            return {
                "has_active_session": True,
                "needs_game": False,
                "game_session_id": str(session.id),
                "fen": session.current_fen or state.fen,
                "white": white,
            }

        return {"has_active_session": False, "needs_game": True}

    async def start_game_and_greet(self, state: ProgressState) -> dict:
        game_service = self._game_svc

        if game_service is None:
            return {"greeting": "Welcome! Let's get started."}

        past_session_count = 0
        try:
            past_sessions = await game_service.get_user_sessions(UUID(state.user_id))
            past_session_count = len(past_sessions)
        except Exception:
            pass

        white = _decide_white(past_session_count)

        try:
            session = GameSession(
                user_id=UUID(state.user_id),
                level=Level(state.level),
                status=GameSessionStatus.ACTIVE,
                initial_fen=state.fen,
                current_fen=state.fen,
                metadata={"white": white},
            )
            session = await game_service.start_new_session(session)
            game_session_id = str(session.id)
        except Exception:
            logger.exception(
                "failed to create game session for user %s", state.user_id)
            return {"greeting": "Welcome! Let's get started."}

        progress_list: list[str] = []
        try:
            all_progress = await game_service.get_all_progress(UUID(state.user_id))
            for pr in all_progress:
                status = "COMPLETE" if pr.topic_completed else "IN_PROGRESS"
                progress_list.append(f"level_{pr.level.value}_{status}")
        except Exception:
            pass

        is_new = len(progress_list) == 0
        name = state.username or "Student"
        side_label = "White" if white == "student" else "Black"

        if is_new:
            greeting = (
                f"Welcome, {name}! I'm Vishy, your chess coach. "
                f"We're starting at Level 1 — Fundamentals & Mechanics. "
                f"Let's begin with the basics and build from there. "
                f"You'll play {side_label} this game — go ahead and make your first move when you're ready!"
            )
        else:
            greeting = (
                f"Welcome back, {name}! Let's pick up where we left off. "
                f"You'll play {side_label} this time. Make your first move when you're ready!"
            )

        return {
            "game_session_id": game_session_id,
            "needs_game": False,
            "has_active_session": True,
            "greeting": greeting,
            "white": white,
        }

    async def resume_session(self, state: ProgressState) -> dict:
        game_service = self._game_svc
        name = state.username or "Student"

        progress_list: list[str] = []
        if game_service is not None:
            try:
                all_progress = await game_service.get_all_progress(UUID(state.user_id))
                for pr in all_progress:
                    status = "COMPLETE" if pr.topic_completed else "IN_PROGRESS"
                    progress_list.append(f"level_{pr.level.value}_{status}")
            except Exception:
                pass

        if progress_list:
            greeting = (
                f"Welcome back, {name}! I've loaded your previous game. "
                f"Let's continue from where we left off."
            )
        else:
            greeting = (
                f"Welcome back, {name}! Let's get started. "
                f"I'll set things up for you."
            )

        return {"greeting": greeting}

    async def check_instructor_turn(self, state: ProgressState) -> dict:
        fen = state.fen
        white = state.white or "student"
        name = state.username or "Student"

        try:
            board = chess.Board(fen)
        except ValueError:
            logger.warning("Invalid FEN in check_instructor_turn: %s", fen)
            return {}

        student_side = "White" if white == "student" else "Black"
        is_instructor_turn = (
            (white == "instructor" and board.turn == chess.WHITE) or
            (white == "student" and board.turn == chess.BLACK)
        )

        if not is_instructor_turn:
            return {
                "greeting": state.greeting + (
                    f" It's your turn, {name}! You're playing {student_side}. "
                    f"Go ahead and make your move."
                ),
            }

        if not self._llm:
            return {}

        legal_moves = [board.san(m) for m in board.legal_moves]
        prompt = INSTRUCTOR_OPENING_PROMPT.format(fen=fen, legal_moves=", ".join(legal_moves))
        messages = [{"role": "user", "content": prompt}]
        instructor_move = ""

        try:
            extracted = await self._llm.generate_structured(messages, NextMoveOutput)
            instructor_move = extracted.move
        except Exception:
            logger.exception("failed to generate instructor opening move")
            return {
                "greeting": state.greeting + (
                    f" I'll start as {student_side}, but I couldn't decide on a move. "
                    f"Something went wrong — please proceed when ready."
                ),
            }

        try:
            move_obj = board.parse_san(instructor_move)
            if move_obj in board.legal_moves:
                board.push(move_obj)
                return {
                    "instructor_move": instructor_move,
                    "instructor_move_fen": board.fen(),
                    "greeting": state.greeting + (
                        f" I'll open as {student_side} with {instructor_move}. "
                        f"Your turn now!"
                    ),
                }
            else:
                logger.warning("Instructor opening move %r not legal, skipping", instructor_move)
        except (ValueError, chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError):
            logger.warning("Instructor opening move %r failed SAN parse, skipping", instructor_move)

        return {
            "greeting": state.greeting + (
                f" I'll play as {student_side}, but I couldn't decide on a move. "
                f"Please proceed when ready."
            ),
        }

    def route_after_check(self, state: ProgressState) -> Literal["start_game_and_greet", "resume_session"]:
        if state.needs_game:
            return "start_game_and_greet"
        return "resume_session"


def build_progress_workflow(upw: UserProgressWorkflow) -> StateGraph:
    builder = StateGraph(ProgressState)

    builder.add_node("check_active_session", upw.check_active_session)
    builder.add_node("start_game_and_greet", upw.start_game_and_greet)
    builder.add_node("resume_session", upw.resume_session)
    builder.add_node("check_instructor_turn", upw.check_instructor_turn)

    builder.set_entry_point("check_active_session")

    builder.add_conditional_edges("check_active_session", upw.route_after_check, {
        "start_game_and_greet": "start_game_and_greet",
        "resume_session": "resume_session",
    })

    builder.add_edge("start_game_and_greet", "check_instructor_turn")
    builder.add_edge("resume_session", "check_instructor_turn")
    builder.add_edge("check_instructor_turn", END)

    return builder


async def run_progress_check(
    user_id: str,
    username: str,
    level: int,
    game_service: GameSvc,
    llm: LLMClient | None = None,
) -> ProgressState:
    graph = build_progress_workflow(UserProgressWorkflow(
        game_service, llm)).compile()

    initial = ProgressState(
        user_id=user_id,
        username=username,
        level=level,
    )

    result = await graph.ainvoke(initial)
    return ProgressState(**result)

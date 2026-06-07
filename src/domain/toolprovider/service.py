from __future__ import annotations

import chess
import chess.engine

import logging
from typing import Any, List, Protocol, Tuple
from uuid import UUID

from langchain_core.tools import StructuredTool

from configs.config import settings
from domain.game.model import Event
from domain.toolprovider.model import (
    EvaluateMoveInput,
    GetCurrentFenInput,
    GetLevelDetailsInput,
    GetSessionHistoryInput,
    GetTopMovesInput,
    ToolError,
    TopMove,
    get_tool_definitions,
)
from domain.instructor.prompt import PromptGetter

logger = logging.getLogger(__name__)


class GameServiceClient(Protocol):
    def get_fen(self) -> str: ...
    async def get_events(self, session_id: UUID, event_types: list[str], limit: int = 100) -> list[Event]: ...


def format_score(pov_score, perspective_turn: bool) -> str:
    color = chess.WHITE if perspective_turn else chess.BLACK
    score = pov_score.pov(color)
    mate_val = score.mate()
    if mate_val is not None:
        sign = "+" if mate_val > 0 else "-"
        return f"M{sign}{abs(mate_val)}"
    cp = score.score(mate_score=10000)
    return f"{cp / 100.0:+.2f}"


class ToolProvider:
    def __init__(
        self,
        game_service: GameServiceClient | None = None,
        game_session_id: str = "",
    ):
        self._game_service = game_service
        self._game_session_id = game_session_id
        self._engine = chess.engine.SimpleEngine.popen_uci(
            settings.stockfish_path)

    def close(self) -> None:
        try:
            self._engine.quit()
        except chess.engine.EngineTerminatedError:
            pass

    def get_definitions(self) -> list[dict[str, Any]]:
        return get_tool_definitions()

    def get_tools(self) -> list[StructuredTool]:
        return [
            StructuredTool.from_function(
                coroutine=self.evaluate_move,
                name="evaluate_move",
                description="Evaluates a chess move using Stockfish. Returns pre-move and post-move scores (centipawn or mate depth) for a given FEN position and a SAN move.",
                args_schema=EvaluateMoveInput,
            ),
            StructuredTool.from_function(
                coroutine=self._get_session_history,
                name="get_session_history",
                description="Returns recent session activity and events",
                args_schema=GetSessionHistoryInput,
            ),
            StructuredTool.from_function(
                coroutine=self._get_level_details,
                name="get_level_details",
                description="Returns curriculum details for a level, or a specific topic within a level",
                args_schema=GetLevelDetailsInput,
            ),
            StructuredTool.from_function(
                coroutine=self.get_top_moves,
                name="get_top_moves",
                description="Returns the top N best moves for a given FEN position using Stockfish, with evaluation scores.",
                args_schema=GetTopMovesInput,
            ),
            StructuredTool.from_function(
                coroutine=self._get_current_fen,
                name="get_current_fen",
                description="Returns the current board position as a FEN string. Use this to get the latest board status before calling other tools that need a FEN.",
                args_schema=GetCurrentFenInput,
            ),
        ]

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "get_session_history": self._get_session_history,
            "evaluate_move": self.evaluate_move,
            "get_level_details": self._get_level_details,
            "get_top_moves": self.get_top_moves,
            "get_current_fen": self._get_current_fen,
        }
        handler = handlers.get(tool_name)
        if handler is None:
            return {"error": f"unknown tool: {tool_name}"}
        return await handler(**arguments)

    async def _get_session_history(self, limit: int = 5, event_types: List[str] = ["move"]) -> dict:
        """Returns recent session activity and events"""
        if self._game_service is None:
            return {"events": [], "error": "game_service not configured"}
        limit = min(int(limit), 50)
        try:
            events = await self._game_service.get_events(UUID(self._game_session_id), event_types, limit)
            history = [
                {
                    "role": e.role.value,
                    "event_type": e.event_type.value,
                    "content": e.payload,
                    "metadata": e.metadata,
                    "created_at": e.created_at.isoformat() if e.created_at else "",
                }
                for e in events
            ]
            logger.info(
                f"get_session_history executed - limit: {limit} event_types: {event_types}")
            return {"events": history}
        except Exception as e:
            return {"events": [], "error": str(e)}

    async def evaluate_move(self, fen: str, san_move: str) -> dict:
        """Evaluates a chess move using Stockfish. Returns pre-move and post-move scores (centipawn or mate depth) for a given FEN position and a SAN move."""
        logger.info(
            "ToolProvider.evaluate_move: fen=%s san_move=%s", fen, san_move)
        if not san_move or not fen:
            logger.warning(
                "ToolProvider.evaluate_move: missing fen or san_move")
            return {"error": "fen and san_move are required"}
        try:
            board = chess.Board(fen)
            move = board.parse_san(san_move)
            init_info = self._engine.analyse(
                board, chess.engine.Limit(depth=15))
            init_score = init_info.get("score")
            if init_score is None:
                logger.warning(
                    "ToolProvider.evaluate_move: engine returned no init score for fen=%s", fen)
                return {"error": "engine returned no score"}
            init_score_str = format_score(init_score, board.turn)
            board.push(move)
            post_info = self._engine.analyse(
                board, chess.engine.Limit(depth=15))
            post_score = post_info.get("score")
            if post_score is None:
                logger.warning(
                    "ToolProvider.evaluate_move: engine returned no post score for fen=%s move=%s", fen, san_move)
                return {"error": "engine returned no score"}
            post_score_str = format_score(post_score, not board.turn)
            result = {"san_move": san_move, "fen": fen,
                      "initial_score": init_score_str, "post_score": post_score_str}
            logger.info(
                "ToolProvider.evaluate_move: success result = %s", result)
            return result
        except (ValueError, chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError) as e:
            logger.warning(
                "ToolProvider.evaluate_move: invalid SAN move %s: %s", san_move, e)
            return {"error": f"invalid SAN move: {e}"}
        except Exception as e:
            logger.exception("ToolProvider.evaluate_move: unexpected error")
            return {"error": str(e)}

    async def _get_level_details(self, level: int = 1, topic: str = "") -> dict:
        """Returns curriculum details for a level, or a specific topic within a level"""
        content = PromptGetter().level_details(level)
        return {"level": level, "content": content, "isComplete": False}

    async def _get_current_fen(self) -> dict:
        """Returns the current board position as a FEN string."""
        logger.info("ToolProvider._get_current_fen called")
        if self._game_service is None:
            return {"error": "game_service not configured"}
        try:
            fen = self._game_service.get_fen()
            logger.info("ToolProvider._get_current_fen: fen=%s", fen)
            return {"fen": fen}
        except Exception as e:
            logger.exception("ToolProvider._get_current_fen: unexpected error")
            return {"error": str(e)}

    async def get_top_moves(self, fen: str, n: int = 3) -> Tuple[List[TopMove], ToolError]:
        """Returns the top N best moves for a given FEN position using Stockfish."""
        logger.info("ToolProvider.get_top_moves: fen=%s n=%s", fen, n)
        n = max(1, min(int(n), 5))
        if not fen:
            logger.warning("ToolProvider.get_top_moves: missing fen")
            return [], ToolError(error="fen is required")
        try:
            board = chess.Board(fen)
            info = self._engine.analyse(
                board, chess.engine.Limit(depth=15), multipv=n)

            moves: list[TopMove] = []
            for entry in info:
                pv = entry.get("pv")
                if not pv:
                    continue
                move = pv[0]
                score = entry.get("score")
                if score is None:
                    continue
                san = board.san(move)
                score_str = format_score(score, board.turn)
                moves.append(TopMove(move=san, score=score_str))
            logger.info(
                "ToolProvider.get_top_moves: success, %d moves", len(moves))
            return moves, ToolError()
        except (ValueError, chess.InvalidMoveError, chess.IllegalMoveError, chess.AmbiguousMoveError) as e:
            logger.warning(
                "ToolProvider.get_top_moves: invalid FEN %s: %s", fen, e)
            return [], ToolError(error=f"invalid FEN: {e}")
        except Exception as e:
            logger.exception("ToolProvider.get_top_moves: unexpected error")
            return [], ToolError(error=str(e))

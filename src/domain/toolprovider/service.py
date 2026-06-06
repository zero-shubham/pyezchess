from __future__ import annotations

import chess
import chess.engine
import json
import logging
from typing import Any
from uuid import UUID

from langchain_core.tools import StructuredTool

from configs.config import settings
from domain.game.service import GameService
from domain.toolprovider.model import (
    EvaluateMoveInput,
    GetLevelDetailsInput,
    GetSessionHistoryInput,
    get_tool_definitions,
)
from domain.instructor.prompt import PromptGetter

logger = logging.getLogger(__name__)


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
        game_service: GameService | None = None,
        game_session_id: str = "",
    ):
        self._game_service = game_service
        self._game_session_id = game_session_id
        self._engine = chess.engine.SimpleEngine.popen_uci(settings.stockfish_path)

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
        ]

    async def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "get_session_history": self._get_session_history,
            "evaluate_move": self.evaluate_move,
            "get_level_details": self._get_level_details,
        }
        handler = handlers.get(name)
        if handler is None:
            return {"error": f"unknown tool: {name}"}
        return await handler(**args)

    async def _get_session_history(self, limit: int = 5, event_type: str = "move") -> dict:
        """Returns recent session activity and events"""
        if self._game_service is None:
            return {"events": [], "error": "game_service not configured"}
        limit = min(int(limit), 50)
        try:
            events = await self._game_service.get_events(UUID(self._game_session_id), limit * 5)
            filtered = [e for e in events if e.event_type.value == event_type][:limit]
            history = [
                {
                    "role": e.role.value,
                    "event_type": e.event_type.value,
                    "content": e.payload,
                    "metadata": e.metadata,
                    "created_at": e.created_at.isoformat() if e.created_at else "",
                }
                for e in filtered
            ]
            return {"events": history}
        except Exception as e:
            return {"events": [], "error": str(e)}

    async def evaluate_move(self, fen: str, san_move: str) -> dict:
        """Evaluates a chess move using Stockfish. Returns pre-move and post-move scores (centipawn or mate depth) for a given FEN position and a SAN move."""
        logger.info("ToolProvider.evaluate_move: fen=%s san_move=%s", fen, san_move)
        if not san_move or not fen:
            logger.warning("ToolProvider.evaluate_move: missing fen or san_move")
            return {"error": "fen and san_move are required"}
        try:
            board = chess.Board(fen)
            move = board.parse_san(san_move)
            init_info = self._engine.analyse(board, chess.engine.Limit(depth=15))
            init_score = init_info.get("score")
            if init_score is None:
                logger.warning("ToolProvider.evaluate_move: engine returned no init score for fen=%s", fen)
                return {"error": "engine returned no score"}
            init_score_str = format_score(init_score, board.turn)
            board.push(move)
            post_info = self._engine.analyse(board, chess.engine.Limit(depth=15))
            post_score = post_info.get("score")
            if post_score is None:
                logger.warning("ToolProvider.evaluate_move: engine returned no post score for fen=%s move=%s", fen, san_move)
                return {"error": "engine returned no score"}
            post_score_str = format_score(post_score, not board.turn)
            result = {"san_move": san_move, "fen": fen, "initial_score": init_score_str, "post_score": post_score_str}
            logger.info("ToolProvider.evaluate_move: success result = %s", result)
            return result
        except ValueError as e:
            logger.exception("ToolProvider.evaluate_move: invalid SAN move %s", san_move)
            return {"error": f"invalid SAN move: {e}"}
        except Exception as e:
            logger.exception("ToolProvider.evaluate_move: unexpected error")
            return {"error": str(e)}

    async def _get_level_details(self, level: int = 1, topic: str = "") -> dict:
        """Returns curriculum details for a level, or a specific topic within a level"""
        content = PromptGetter().level_details(level)
        return {"level": level, "content": content, "isComplete": False}
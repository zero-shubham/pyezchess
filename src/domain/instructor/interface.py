from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from domain.instructor.model import ExplainResult, MovePlayedResult


class Instructor(ABC):
    @abstractmethod
    async def begin_game(self, game_svc: Any, user_id: str, username: str, level: int) -> ExplainResult: ...

    @abstractmethod
    async def handle_move(self, game_svc: Any, move: str, fen: str, game_session_id: str,
                          user_id: str, username: str, level: int,
                          legal_moves: list[str] | None = None,
                          white: str | None = None) -> MovePlayedResult: ...
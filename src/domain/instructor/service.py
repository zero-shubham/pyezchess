from __future__ import annotations

import logging
from typing import Any

from domain.instructor.interface import Instructor
from domain.instructor.model import ExplainResult, LLMClient, MovePlayedResult
from domain.instructor.workflows.move import run_move_workflow
from domain.instructor.workflows.progress import run_progress_check

logger = logging.getLogger(__name__)


class LangGraphInstructor(Instructor):
    def __init__(
        self,
        llm: LLMClient,
        system_prompt: str = "",
        user_id: str = "",
    ):
        self._llm = llm
        self._system_prompt = system_prompt
        self._user_id = user_id

    async def begin_game(self, game_svc: Any, user_id: str, username: str, level: int) -> ExplainResult:
        result = await run_progress_check(
            user_id=user_id,
            username=username,
            level=level,
            game_service=game_svc,
            llm=self._llm,
        )

        return ExplainResult(
            explanation=result.greeting,
            game_session_id=result.game_session_id,
            fen=result.instructor_move_fen or result.fen,
            white=result.white,
            instructor_move=result.instructor_move,
        )

    async def handle_move(self, game_svc: Any, move: str, fen: str, game_session_id: str,
                          user_id: str, username: str, level: int,
                          legal_moves: list[str] | None = None,
                          white: str | None = None) -> MovePlayedResult:
        result = await run_move_workflow(
            fen=fen,
            move=move,
            user_id=user_id,
            username=username,
            level=level,
            game_session_id=game_session_id,
            llm=self._llm,
            game_svc=game_svc,
            legal_moves=legal_moves,
            white=white,
        )

        return MovePlayedResult(
            valid=True,
            fen=result.fen,
            explanation=result.message,
            move=result.next_move,
            score=result.score_delta,
            score_grade=result.score_grade,
            is_best=result.score_grade == "STRONG",
            commentary=result.commentary,
        )
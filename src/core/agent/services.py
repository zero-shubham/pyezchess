from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from core.agent.interfaces import Instructor
from core.agent.models import ExplainResult, LLMClient, MovePlayedResult, QueryResult
from core.agent.workflows.move import run_move_workflow
from core.agent.workflows.progress import run_progress_check
from core.agent.workflows.query import run_query_workflow

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

    async def _persist_token_usage(
        self, game_svc: Any, session_id: str, input_tokens: int, output_tokens: int
    ) -> None:
        await game_svc.increment_token_usage(UUID(session_id), input_tokens, output_tokens)

    def _make_token_persist(self, game_svc: Any):
        async def _persist(session_id: str, input_tokens: int, output_tokens: int) -> None:
            await self._persist_token_usage(game_svc, session_id, input_tokens, output_tokens)
        return _persist

    async def begin_game(self, game_svc: Any, user_id: str, username: str, level: int) -> ExplainResult:
        result = await run_progress_check(
            user_id=user_id,
            username=username,
            level=level,
            game_service=game_svc,
            llm=self._llm,
            token_persist=self._make_token_persist(game_svc),
        )

        return ExplainResult(
            explanation=result.greeting,
            game_session_id=result.game_session_id,
            fen=result.instructor_move_fen or result.fen,
            white=result.white,
            instructor_move=result.instructor_move,
            captured=result.captured,
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
            token_persist=self._make_token_persist(game_svc),
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

    async def handle_query(self, game_svc: Any, query: str, game_session_id: str,
                           user_id: str, username: str, level: int,
                           fen: str, white: str) -> QueryResult:
        result = await run_query_workflow(
            query=query,
            game_session_id=game_session_id,
            user_id=user_id,
            username=username,
            level=level,
            fen=fen,
            white=white,
            llm=self._llm,
            game_svc=game_svc,
            token_persist=self._make_token_persist(game_svc),
        )
        return QueryResult(explanation=result.explanation)

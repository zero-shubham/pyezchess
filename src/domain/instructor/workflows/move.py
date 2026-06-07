from __future__ import annotations

import logging
import asyncio
from dataclasses import dataclass, field
from typing import Annotated, Protocol, runtime_checkable
from uuid import UUID

from chess import Board
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.runtime import Runtime


from domain.game.model import Event, EventRole, EventType
from domain.instructor.model import LLMClient, MessageOutput, NextMoveOutput, ScoreOutput, ToolExecutor
from domain.instructor.prompt import PromptGetter
from domain.toolprovider.service import ToolProvider
from domain.game.board import EzBoard

logger = logging.getLogger(__name__)


@dataclass
class MoveState:
    fen: str = ""
    move: str = ""
    user_id: str = ""
    username: str = ""
    level: int = 1
    game_session_id: str = ""

    white: str = "student"

    commentary: str = ""
    next_move: str = ""
    score_delta: int = 0
    score_reason: str = ""
    score_grade: str = ""
    message: str = ""

    legal_moves: list[str] = field(default_factory=list)
    invalid_move: str = ""

    messages: Annotated[list[BaseMessage], add_messages] = field(default_factory=list)
    _current_step: str = ""
    _pre_fen: str = ""
    _analysis: str = ""
    _top_moves_str: str = ""


@dataclass
class MoveContext:
    game_session_id: str


@runtime_checkable
class GameSvcProto(Protocol):
    board: EzBoard
    async def add_event(self, event: Event) -> Event: ...
    async def persist_fen(self, game_session_id: UUID, fen: str) -> None: ...


COMMENTARY_PROMPT = """Workflow: move, step: compute_commentary

FEN: {fen}
Student move: {move}
Score: {grade} ({delta:+d}) — {reason}

Give 2-3 sentences of commentary on the student's move. Describe what it accomplishes or what idea it expresses on the board. Base your commentary on the score above — acknowledge strong moves, lead with curiosity for weak ones.

If required, use the get_session_history tool to retrieve past events from this game session for additional context."""

INSTRUCTOR_MOVE_PROMPT = """Workflow: move, step: compute_next_move

FEN (after student move): {fen}
Student move: {move}

You (Vishy) are playing as {vishy_color}. The student is {student_color}.

Stockfish top 3 candidate moves for this position:
{top_moves}

Evaluate these candidates further with evaluate_move to determine the best reply. You may also evaluate other candidates if you see a strong alternative not listed above. Prefer developing moves over passive ones, and tactical threats over quiet moves when the position permits.

If required, use the get_session_history tool to retrieve past events from this game session for additional context."""

INSTRUCTOR_MOVE_RETRY_PROMPT = """Workflow: move, step: regenerate_move

FEN (after student move): {fen}
Student move: {move}
Previous move "{invalid_move}" was invalid.

Legal moves: {legal_moves}

You (Vishy) are playing as {vishy_color}. The student is {student_color}.

Stockfish top 3 candidate moves for this position:
{top_moves}

Evaluate these candidates from the legal moves list using evaluate_move. Pick the strongest move available. Focus on maintaining positional advantage.

If required, use the get_session_history tool to retrieve past events from this game session for additional context."""

SCORE_PROMPT = """Workflow: move, step: compute_score

FEN (before student move): {fen}
Student move: {move}

Stockfish evaluation for this move:
- Initial score (before move): {init_score}
- Post score (after move): {post_score}

Grade the student's move based on the evaluation above. Be generous with beginners — err toward GOOD or STRONG when the student shows sound reasoning even if the computer prefers a different move.

If required, use the get_session_history tool to retrieve past events from this game session for additional context."""

SCORE_EXTRACT_PROMPT = """Workflow: move, step: compute_score (extraction)

FEN (before student move): {fen}
Student move: {move}

Stockfish evaluation for this move:
- Initial score (before move): {init_score}
- Post score (after move): {post_score}

Analysis results:
{analysis}

Grade the student's move based on the evaluation above. Be generous with beginners — err toward GOOD or STRONG when the student shows sound reasoning even if the computer prefers a different move."""

MESSAGE_PROMPT = """Workflow: move, step: compute_message

FEN (after student move): {fen}
Student move: {move}
Instructor response: {next_move}

Explain to the student why {next_move} was chosen in response. 2-3 sentences."""

MOVE_EXTRACT_PROMPT = """Workflow: move, step: compute_next_move (extraction)

FEN (after student move): {fen}
Student move: {move}

You (Vishy) are playing as {vishy_color}. The student is {student_color}.

Position analysis results:
{analysis}

Choose the single best response move based on the evaluation data."""

MOVE_RETRY_EXTRACT_PROMPT = """Workflow: move, step: regenerate_move (extraction)

FEN (after student move): {fen}
Student move: {move}

You (Vishy) are playing as {vishy_color}. The student is {student_color}.

Legal moves: {legal_moves}

Position analysis results:
{analysis}

Previous move "{invalid_move}" was invalid. Choose the best move from the legal moves list based on the evaluation data."""




def _player_colors(white: str) -> tuple[str, str]:
    if white == "instructor":
        return ("white", "black")
    return ("black", "white")


class _WorkflowBase:
    def __init__(self, llm: LLMClient, tools: list[BaseTool]) -> None:
        self._llm = llm
        self._tools = tools
        self._llm_with_tools = llm.bind_tools(self._tools)

    @staticmethod
    def _system_prompt() -> str:
        try:
            return PromptGetter().main_prompt()
        except Exception:
            return ""

    def _build_messages(self, system_content: str, *, no_tool: bool = False) -> list[BaseMessage]:
        messages: list[BaseMessage] = []
        system = self._system_prompt()
        if system:
            messages.append(SystemMessage(content=system))
        if no_tool:
            system_content = system_content.rstrip() + "\n\nNO_TOOL"
        messages.append(SystemMessage(content=system_content))
        return messages

    @staticmethod
    def _last_message_content(state) -> str:
        if state.messages:
            return str(getattr(state.messages[-1], "content", "") or "")
        return ""

    def _make_llm_node(self, step: str):
        async def node(state) -> dict:
            logger.info(f"CONTEXT HAS {len(state.messages)} messages")
            response = await self._llm_with_tools.ainvoke(state.messages)
            return {"messages": [response], "_current_step": step}
        return node


class EvaluateWorkflow(_WorkflowBase):
    def __init__(self, llm: LLMClient, game_svc: GameSvcProto, tool_executor: ToolExecutor, tools: list[BaseTool]) -> None:
        super().__init__(llm, tools)
        self._game_svc = game_svc
        self._tool_executor = tool_executor
        self._llm_structured_score = llm.with_structured_output(ScoreOutput)

    async def _prepare_score(self, state: MoveState, runtime: Runtime[MoveContext]) -> dict:
        board = self._game_svc.board
        try:
            board.parse_san(state.move)
        except ValueError:
            logger.exception("failed to parse move %s in _prepare_score", state.move)
            return {}

        pre_fen = board.fen()
        try:
            eval_result = await self._tool_executor.execute(
                "evaluate_move", {"fen": pre_fen, "san_move": state.move})
            if "error" in eval_result:
                raise ValueError(f"engine evaluation failed: {eval_result['error']}")
        except Exception:
            logger.exception("failed to evaluate move, using defaults")
            eval_result = {"initial_score": "N/A", "post_score": "N/A"}

        prompt = SCORE_PROMPT.format(
            fen=pre_fen, move=state.move,
            init_score=eval_result.get("initial_score", "N/A"),
            post_score=eval_result.get("post_score", "N/A"),
        )
        return {
            "messages": self._build_messages(prompt),
            "_pre_fen": pre_fen,
        }

    async def _structured_score(self, state: MoveState, runtime: Runtime[MoveContext]) -> dict:
        board = self._game_svc.board

        raw_text = self._last_message_content(state).strip()
        prompt = SCORE_EXTRACT_PROMPT.format(
            fen=state._pre_fen, move=state.move,
            init_score="N/A", post_score="N/A",
            analysis=raw_text,
        )
        messages = self._build_messages(prompt, no_tool=True)
        result = await self._llm_structured_score.ainvoke(messages)
        grade = result.grade if result else "GOOD"
        delta = result.delta if result else 1
        reason = result.reason if result else ""
        logger.info("structured_score: grade=%s delta=%d reason=%s", grade, delta, reason)

        try:
            move_obj = board.parse_san(state.move)
        except ValueError:
            logger.exception("failed to parse move in _extract_score")
            move_obj = None

        if move_obj:
            board.push(move_obj)
        post_fen = board.fen()
        legal_moves = board.get_legal_moves_san()

        try:
            await self._game_svc.persist_fen(UUID(state.game_session_id), post_fen)
        except Exception:
            logger.exception("failed to persist fen")

        try:
            await self._game_svc.add_event(Event(
                game_session_id=UUID(state.game_session_id),
                user_id=UUID(state.user_id),
                role=EventRole.STUDENT,
                event_type=EventType.MOVE,
                metadata={"move": state.move, "fen": post_fen},
            ))
        except Exception:
            logger.exception("failed to record student move event")

        return {
            "fen": post_fen,
            "legal_moves": legal_moves,
            "score_delta": delta,
            "score_reason": reason,
            "score_grade": grade,
        }

    async def _prepare_commentary(self, state: MoveState, runtime: Runtime[MoveContext]) -> dict:
        prompt = COMMENTARY_PROMPT.format(
            fen=state.fen, move=state.move,
            grade=state.score_grade, delta=state.score_delta,
            reason=state.score_reason,
        )

        return {
            "messages": self._build_messages(prompt),
        }

    async def _extract_commentary(self, state: MoveState) -> dict:
        commentary = self._last_message_content(state).strip()
        return {"commentary": commentary}


class InstructorMoveWorkflow(_WorkflowBase):
    def __init__(self, llm: LLMClient, game_svc: GameSvcProto, tool_provider: ToolProvider, tools: list[BaseTool]) -> None:
        super().__init__(llm, tools)
        self._game_svc = game_svc
        self._tool_provider = tool_provider
        self._llm_structured_move = llm.with_structured_output(NextMoveOutput)
        self._llm_structured_message = llm.with_structured_output(MessageOutput)

    async def _get_top_moves_str(self, fen: str) -> str:
        try:
            moves, err = await self._tool_provider.get_top_moves(fen, n=3)
            if err.error:
                logger.warning("get_top_moves returned error: %s", err.error)
                return "Unavailable"
            lines = [f"{i}. {m.move} ({m.score})" for i, m in enumerate(moves, 1)]
            return "\n".join(lines)
        except Exception:
            logger.exception("failed to get top moves")
            return "Unavailable"

    async def _prepare_move_analysis(self, state: MoveState) -> dict:
        vishy_color, student_color = _player_colors(state.white)
        top_moves_str = await self._get_top_moves_str(state.fen)
        prompt = INSTRUCTOR_MOVE_PROMPT.format(
            fen=state.fen, move=state.move,
            vishy_color=vishy_color, student_color=student_color,
            top_moves=top_moves_str)
        return {
            "messages": self._build_messages(prompt),
            "_top_moves_str": top_moves_str,
        }

    async def _structured_next_move(self, state: MoveState) -> dict:
        raw_text = self._last_message_content(state).strip()
        vishy_color, student_color = _player_colors(state.white)
        prompt = MOVE_EXTRACT_PROMPT.format(
            fen=state.fen, move=state.move,
            vishy_color=vishy_color, student_color=student_color,
            analysis=raw_text)
        messages = self._build_messages(prompt, no_tool=True)
        result = await self._llm_structured_move.ainvoke(messages)
        next_move = result.move if result else ""
        logger.info("structured_next_move: move=%s", next_move)
        return {"next_move": next_move, "invalid_move": "", "_current_step": "validate"}

    async def _prepare_move_retry(self, state: MoveState) -> dict:
        vishy_color, student_color = _player_colors(state.white)
        invalid_move = state.next_move or state.invalid_move
        top_moves_str = state._top_moves_str or await self._get_top_moves_str(state.fen)
        prompt = INSTRUCTOR_MOVE_RETRY_PROMPT.format(
            fen=state.fen, move=state.move, invalid_move=invalid_move,
            legal_moves=", ".join(state.legal_moves),
            vishy_color=vishy_color, student_color=student_color,
            top_moves=top_moves_str)
        return {
            "messages": self._build_messages(prompt),
            "_current_step": "move_retry",
            "_top_moves_str": top_moves_str,
        }

    async def _structured_retry_move(self, state: MoveState) -> dict:
        raw_text = self._last_message_content(state).strip()
        vishy_color, student_color = _player_colors(state.white)
        invalid_move = state.next_move or state.invalid_move
        prompt = MOVE_RETRY_EXTRACT_PROMPT.format(
            fen=state.fen, move=state.move,
            legal_moves=", ".join(state.legal_moves),
            invalid_move=invalid_move, analysis=raw_text,
            vishy_color=vishy_color, student_color=student_color)
        messages = self._build_messages(prompt, no_tool=True)
        result = await self._llm_structured_move.ainvoke(messages)
        next_move = result.move if result else ""
        logger.info("structured_retry_move: move=%s", next_move)
        return {"next_move": next_move, "invalid_move": invalid_move, "_current_step": "validate"}

    async def _generate_message(self, state: MoveState) -> dict:
        prompt = MESSAGE_PROMPT.format(
            fen=state.fen, move=state.move, next_move=state.next_move)
        messages = self._build_messages(prompt, no_tool=True)
        result = await self._llm_structured_message.ainvoke(messages)
        message = result.message if result else ""
        if state.game_session_id and state.next_move:
            try:
                await self._game_svc.add_event(Event(
                    game_session_id=UUID(state.game_session_id),
                    user_id=UUID(state.user_id),
                    role=EventRole.INSTRUCTOR,
                    event_type=EventType.MOVE,
                    metadata={"move": state.next_move, "fen": state.fen},
                ))
            except Exception:
                logger.exception("failed to record instructor move event")
            try:
                await self._game_svc.add_event(Event(
                    game_session_id=UUID(state.game_session_id),
                    user_id=UUID(state.user_id),
                    role=EventRole.INSTRUCTOR,
                    event_type=EventType.EXPLAIN,
                    metadata={"message": message, "move": state.move},
                ))
            except Exception:
                logger.exception("failed to record instructor explain event")
        return {"message": message, "_current_step": "done"}


def _route_evaluate_tools_back(state: MoveState) -> str:
    mapping = {
        "score": "llm_score",
        "commentary": "llm_commentary",
    }
    return mapping.get(state._current_step, END)


def _route_move_tools_back(state: MoveState) -> str:
    mapping = {
        "analysis": "llm_analysis",
        "move_retry": "llm_retry",
    }
    return mapping.get(state._current_step, END)


def _route_after_validate(state: MoveState) -> str:
    if not state.next_move:
        return "prepare_move_retry"
    if state.legal_moves and state.next_move not in state.legal_moves:
        return "prepare_move_retry"
    return "prepare_message"


def build_evaluate_workflow(ew: EvaluateWorkflow) -> StateGraph:
    builder = StateGraph(MoveState, context_schema=MoveContext)

    builder.add_node("start", lambda state: {})

    builder.add_node("prepare_score", ew._prepare_score)
    builder.add_node("structured_score", ew._structured_score)
    builder.add_node("prepare_commentary", ew._prepare_commentary)
    builder.add_node("extract_commentary", ew._extract_commentary)

    builder.add_node("llm_score", ew._make_llm_node("score"))
    builder.add_node("llm_commentary", ew._make_llm_node("commentary"))

    builder.add_node("tools", ToolNode(ew._tools))

    builder.set_entry_point("start")
    builder.add_edge("start", "prepare_score")

    builder.add_edge("prepare_score", "llm_score")
    builder.add_conditional_edges("llm_score", tools_condition, {"tools": "tools", END: "structured_score"})
    builder.add_edge("structured_score", "prepare_commentary")

    builder.add_edge("prepare_commentary", "llm_commentary")
    builder.add_conditional_edges("llm_commentary", tools_condition, {"tools": "tools", END: "extract_commentary"})
    builder.add_edge("extract_commentary", END)

    builder.add_conditional_edges("tools", _route_evaluate_tools_back)

    return builder


def build_instructor_move_workflow(imw: InstructorMoveWorkflow) -> StateGraph:
    builder = StateGraph(MoveState, context_schema=MoveContext)

    builder.add_node("start", lambda state: {})

    builder.add_node("prepare_move_analysis", imw._prepare_move_analysis)
    builder.add_node("structured_next_move", imw._structured_next_move)
    builder.add_node("prepare_move_retry", imw._prepare_move_retry)
    builder.add_node("structured_retry_move", imw._structured_retry_move)
    builder.add_node("generate_message", imw._generate_message)

    builder.add_node("llm_analysis", imw._make_llm_node("analysis"))
    builder.add_node("llm_retry", imw._make_llm_node("move_retry"))

    builder.add_node("tools", ToolNode(imw._tools))

    builder.set_entry_point("start")
    builder.add_edge("start", "prepare_move_analysis")

    builder.add_edge("prepare_move_analysis", "llm_analysis")
    builder.add_conditional_edges("llm_analysis", tools_condition, {"tools": "tools", END: "structured_next_move"})

    builder.add_conditional_edges("structured_next_move", _route_after_validate, {
        "prepare_move_retry": "prepare_move_retry",
        "prepare_message": "generate_message",
    })

    builder.add_edge("prepare_move_retry", "llm_retry")
    builder.add_conditional_edges("llm_retry", tools_condition, {"tools": "tools", END: "structured_retry_move"})
    builder.add_conditional_edges("structured_retry_move", _route_after_validate, {
        "prepare_move_retry": "prepare_move_retry",
        "prepare_message": "generate_message",
    })

    builder.add_edge("generate_message", END)

    builder.add_conditional_edges("tools", _route_move_tools_back)

    return builder


async def run_move_workflow(
    fen: str,
    move: str,
    user_id: str,
    username: str,
    level: int,
    game_session_id: str,
    llm: LLMClient,
    game_svc: GameSvcProto,
    legal_moves: list[str] | None = None,
    white: str | None = None,
) -> MoveState:
    tool_provider = ToolProvider(game_service=game_svc, game_session_id=game_session_id)
    try:
        evaluate_tools = tool_provider.get_tools()
        instructor_move_tools = tool_provider.get_tools()

        ew = EvaluateWorkflow(llm, game_svc, tool_provider, tools=evaluate_tools)
        imw = InstructorMoveWorkflow(llm, game_svc, tool_provider, tools=instructor_move_tools)

        eval_graph = build_evaluate_workflow(ew).compile()
        eval_result = await asyncio.shield(eval_graph.ainvoke(
            MoveState(
                fen=fen,
                move=move,
                user_id=user_id,
                username=username,
                level=level,
                game_session_id=game_session_id,
                white=white or "student",
            ),
            context=MoveContext(game_session_id=game_session_id),
        ))

        eval_state = MoveState(**eval_result)

        move_graph = build_instructor_move_workflow(imw).compile()
        move_result = await asyncio.shield(move_graph.ainvoke(
            MoveState(
                fen=eval_state.fen,
                move=eval_state.move,
                user_id=eval_state.user_id,
                username=eval_state.username,
                level=eval_state.level,
                game_session_id=eval_state.game_session_id,
                white=eval_state.white,
                legal_moves=eval_state.legal_moves,
            ),
            context=MoveContext(game_session_id=game_session_id),
        ))

        move_state = MoveState(**move_result)

        return MoveState(
            fen=move_state.fen,
            move=eval_state.move,
            user_id=eval_state.user_id,
            username=eval_state.username,
            level=eval_state.level,
            game_session_id=eval_state.game_session_id,
            white=eval_state.white,
            commentary=eval_state.commentary,
            next_move=move_state.next_move,
            score_delta=eval_state.score_delta,
            score_reason=eval_state.score_reason,
            score_grade=eval_state.score_grade,
            message=move_state.message,
            legal_moves=move_state.legal_moves,
            invalid_move=move_state.invalid_move,
        )
    finally:
        tool_provider.close()
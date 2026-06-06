from __future__ import annotations

import json
import logging
import asyncio
from dataclasses import dataclass, field
from typing import Annotated, Protocol, runtime_checkable
from uuid import UUID, uuid4

from chess import Board
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.runtime import Runtime
from langgraph.store.postgres.aio import AsyncPostgresStore

from domain.game.model import Event, EventRole, EventType
from domain.instructor.model import LLMClient, NextMoveOutput, ScoreOutput, ToolExecutor
from domain.instructor.prompt import PromptGetter
from domain.toolprovider.service import ToolProvider

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


@dataclass
class MoveContext:
    game_session_id: str


@runtime_checkable
class GameSvcProto(Protocol):
    board: Board
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

Use evaluate_move to analyze candidate moves. Focus on finding the strongest reply that maintains or builds positional advantage. Prefer developing moves over passive ones, and tactical threats over quiet moves when the position permits.

If required, use the get_session_history tool to retrieve past events from this game session for additional context."""

INSTRUCTOR_MOVE_RETRY_PROMPT = """Workflow: move, step: regenerate_move

FEN (after student move): {fen}
Student move: {move}
Previous move "{invalid_move}" was invalid.

Legal moves: {legal_moves}

You (Vishy) are playing as {vishy_color}. The student is {student_color}.

Use evaluate_move to analyze candidates from the legal moves list. Pick the strongest move available. Focus on maintaining positional advantage.

If required, use the get_session_history tool to retrieve past events from this game session for additional context."""

SCORE_PROMPT = """Workflow: move, step: compute_score

FEN (before student move): {fen}
Student move: {move}

Stockfish evaluation for this move:
- Initial score (before move): {init_score}
- Post score (after move): {post_score}

Grade the student's move based on the evaluation above. Be generous with beginners — err toward GOOD or STRONG when the student shows sound reasoning even if the computer prefers a different move.

If required, use the get_session_history tool to retrieve past events from this game session for additional context."""

MESSAGE_PROMPT = """Workflow: move, step: compute_message

FEN (after student move): {fen}
Student move: {move}
Instructor response: {next_move}

Explain to the student why {next_move} was chosen in response. 2-3 sentences.

If required, use the get_session_history tool to retrieve past events from this game session for additional context."""

MOVE_EXTRACT_PROMPT = """Workflow: move, step: compute_next_move (extraction)

FEN (after student move): {fen}
Student move: {move}

You (Vishy) are playing as {vishy_color}. The student is {student_color}.

Position analysis results:
{analysis}

Choose the single best response move based on the evaluation data.

If required, use the get_session_history tool to retrieve past events from this game session for additional context."""

MOVE_RETRY_EXTRACT_PROMPT = """Workflow: move, step: regenerate_move (extraction)

FEN (after student move): {fen}
Student move: {move}

You (Vishy) are playing as {vishy_color}. The student is {student_color}.

Legal moves: {legal_moves}

Position analysis results:
{analysis}

Previous move "{invalid_move}" was invalid. Choose the best move from the legal moves list based on the evaluation data.

If required, use the get_session_history tool to retrieve past events from this game session for additional context."""

SCORE_OUTPUT_TOOL = StructuredTool.from_function(
    func=lambda grade, delta, reason: json.dumps({"grade": grade, "delta": delta, "reason": reason}),
    name="ScoreOutput",
    description="Output the score assessment for the student's move",
    args_schema=ScoreOutput,
)

NEXT_MOVE_OUTPUT_TOOL = StructuredTool.from_function(
    func=lambda move: json.dumps({"move": move}),
    name="NextMoveOutput",
    description="Output the chosen chess move in SAN notation",
    args_schema=NextMoveOutput,
)


def _player_colors(white: str) -> tuple[str, str]:
    """Return (vishy_color, student_color) based on who plays white."""
    if white == "instructor":
        return ("white", "black")
    return ("black", "white")


class MoveWorkflow:
    def __init__(self, llm: LLMClient, game_svc: GameSvcProto, tool_executor: ToolExecutor, tools: list[BaseTool]) -> None:
        self._llm = llm
        self._game_svc = game_svc
        self._tool_executor = tool_executor
        self._tools = tools
        self._llm_with_tools = llm.bind_tools(self._tools)

    @staticmethod
    def _system_prompt() -> str:
        try:
            return PromptGetter().main_prompt()
        except Exception:
            return ""

    def _build_messages(self, system_content: str) -> list[BaseMessage]:
        messages: list[BaseMessage] = []
        system = self._system_prompt()
        if system:
            messages.append(SystemMessage(content=system))
        messages.append(SystemMessage(content=system_content))
        return messages

    def _parse_structured_tool(self, message: BaseMessage) -> dict:
        content = str(message.content or "")
        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return {}

    def _last_message_content(self, state: MoveState) -> str:
        if state.messages:
            return str(getattr(state.messages[-1], "content", "") or "")
        return ""

    def _make_llm_node(self, step: str):
        async def node(state: MoveState) -> dict:
            response = await self._llm_with_tools.ainvoke(state.messages)
            return {"messages": [response], "_current_step": step}
        return node

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

    async def _extract_score(self, state: MoveState, runtime: Runtime[MoveContext]) -> dict:
        board = self._game_svc.board

        grade = "GOOD"
        delta = 1
        reason = ""
        if state.messages:
            parsed = self._parse_structured_tool(state.messages[-1])
            grade = parsed.get("grade", "GOOD")
            delta = int(parsed.get("delta", 1))
            reason = parsed.get("reason", "")
            logger.info("extract_score: grade=%s delta=%d reason=%s", grade, delta, reason)

        try:
            move_obj = board.parse_san(state.move)
        except ValueError:
            logger.exception("failed to parse move in _extract_score")
            move_obj = None

        if move_obj:
            board.push(move_obj)
        post_fen = board.fen()
        legal_moves = [board.san(m) for m in board.legal_moves]

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

        if runtime and runtime.store:
            try:
                namespace = ("games", runtime.context.game_session_id)
                summary = f"Move {state.move}: {grade} - {reason}"
                await runtime.store.aput(
                    namespace, str(uuid4()),
                    {"summary": summary, "move": state.move,
                     "grade": grade, "delta": delta, "reason": reason},
                )
            except Exception:
                logger.exception("failed to store game memory")

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
        if runtime and runtime.store:
            try:
                namespace = ("games", runtime.context.game_session_id)
                memories = await runtime.store.asearch(namespace, query=state.move, limit=5)
                past_summaries = "\n".join(
                    m.value.get("summary", "") for m in memories if m.value.get("summary")
                )
                if past_summaries:
                    prompt += f"\n\nContext from previous moves in this game:\n{past_summaries}"
            except Exception:
                logger.exception("failed to search game memories for commentary")

        return {
            "messages": self._build_messages(prompt),
        }

    async def _extract_commentary(self, state: MoveState) -> dict:
        commentary = self._last_message_content(state).strip()
        return {"commentary": commentary}

    async def _prepare_move_analysis(self, state: MoveState) -> dict:
        vishy_color, student_color = _player_colors(state.white)
        prompt = INSTRUCTOR_MOVE_PROMPT.format(
            fen=state.fen, move=state.move,
            vishy_color=vishy_color, student_color=student_color)
        return {
            "messages": self._build_messages(prompt),
        }

    async def _extract_move_analysis(self, state: MoveState) -> dict:
        raw_text = self._last_message_content(state).strip()
        vishy_color, student_color = _player_colors(state.white)
        prompt = MOVE_EXTRACT_PROMPT.format(
            fen=state.fen, move=state.move,
            vishy_color=vishy_color, student_color=student_color,
            analysis=raw_text)
        return {
            "messages": self._build_messages(prompt),
            "_analysis": raw_text,
        }

    async def _extract_next_move(self, state: MoveState) -> dict:
        next_move = ""
        if state.messages:
            parsed = self._parse_structured_tool(state.messages[-1])
            next_move = parsed.get("move", "")
        logger.info("extract_next_move: move=%s", next_move)
        return {"next_move": next_move, "invalid_move": "", "_current_step": "validate"}

    async def _prepare_move_retry(self, state: MoveState) -> dict:
        vishy_color, student_color = _player_colors(state.white)
        invalid_move = state.next_move or state.invalid_move
        prompt = INSTRUCTOR_MOVE_RETRY_PROMPT.format(
            fen=state.fen, move=state.move, invalid_move=invalid_move,
            legal_moves=", ".join(state.legal_moves),
            vishy_color=vishy_color, student_color=student_color)
        return {
            "messages": self._build_messages(prompt),
            "_current_step": "move_retry",
        }

    async def _extract_move_retry(self, state: MoveState) -> dict:
        raw_text = self._last_message_content(state).strip()
        vishy_color, student_color = _player_colors(state.white)
        invalid_move = state.next_move or state.invalid_move
        prompt = MOVE_RETRY_EXTRACT_PROMPT.format(
            fen=state.fen, move=state.move,
            legal_moves=", ".join(state.legal_moves),
            invalid_move=invalid_move, analysis=raw_text,
            vishy_color=vishy_color, student_color=student_color)
        return {
            "messages": self._build_messages(prompt),
            "_current_step": "move_retry_extraction",
            "_analysis": raw_text,
        }

    async def _extract_retry_move(self, state: MoveState) -> dict:
        next_move = ""
        if state.messages:
            parsed = self._parse_structured_tool(state.messages[-1])
            next_move = parsed.get("move", "")
        invalid_move = state.next_move or state.invalid_move
        logger.info("extract_retry_move: move=%s", next_move)
        return {"next_move": next_move, "invalid_move": invalid_move, "_current_step": "validate"}

    async def _prepare_message(self, state: MoveState) -> dict:
        prompt = MESSAGE_PROMPT.format(
            fen=state.fen, move=state.move, next_move=state.next_move)
        return {
            "messages": self._build_messages(prompt),
            "_current_step": "message",
        }

    async def _extract_message(self, state: MoveState) -> dict:
        message = self._last_message_content(state).strip()
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


def _route_tools_back(state: MoveState) -> str:
    for msg in reversed(state.messages):
        if not hasattr(msg, "name"):
            break
        if msg.name == "ScoreOutput":
            return "extract_score"
        if msg.name == "NextMoveOutput":
            if state._current_step == "move_extract":
                return "extract_next_move"
            return "extract_retry_move"

    mapping = {
        "score": "llm_score",
        "commentary": "llm_commentary",
        "analysis": "llm_analysis",
        "move_extract": "llm_move_extract",
        "retry": "llm_retry",
        "retry_extract": "llm_retry_extract",
        "message": "llm_message",
    }
    return mapping.get(state._current_step, END)


def _route_after_validate(state: MoveState) -> str:
    if not state.next_move:
        return "prepare_move_retry"
    if state.legal_moves and state.next_move not in state.legal_moves:
        return "prepare_move_retry"
    return "prepare_message"


def build_move_workflow(mw: MoveWorkflow) -> StateGraph:
    builder = StateGraph(MoveState, context_schema=MoveContext)

    builder.add_node("start", lambda state: {})

    builder.add_node("prepare_score", mw._prepare_score)
    builder.add_node("extract_score", mw._extract_score)
    builder.add_node("prepare_commentary", mw._prepare_commentary)
    builder.add_node("extract_commentary", mw._extract_commentary)
    builder.add_node("prepare_move_analysis", mw._prepare_move_analysis)
    builder.add_node("extract_move_analysis", mw._extract_move_analysis)
    builder.add_node("extract_next_move", mw._extract_next_move)
    builder.add_node("prepare_move_retry", mw._prepare_move_retry)
    builder.add_node("extract_move_retry", mw._extract_move_retry)
    builder.add_node("extract_retry_move", mw._extract_retry_move)
    builder.add_node("prepare_message", mw._prepare_message)
    builder.add_node("extract_message", mw._extract_message)

    builder.add_node("llm_score", mw._make_llm_node("score"))
    builder.add_node("llm_commentary", mw._make_llm_node("commentary"))
    builder.add_node("llm_analysis", mw._make_llm_node("analysis"))
    builder.add_node("llm_move_extract", mw._make_llm_node("move_extract"))
    builder.add_node("llm_retry", mw._make_llm_node("retry"))
    builder.add_node("llm_retry_extract", mw._make_llm_node("retry_extract"))
    builder.add_node("llm_message", mw._make_llm_node("message"))

    builder.add_node("tools", ToolNode(mw._tools))

    builder.set_entry_point("start")
    builder.add_edge("start", "prepare_score")

    builder.add_edge("prepare_score", "llm_score")
    builder.add_conditional_edges("llm_score", tools_condition, {"tools": "tools", END: "extract_score"})
    builder.add_edge("extract_score", "prepare_commentary")

    builder.add_edge("prepare_commentary", "llm_commentary")
    builder.add_conditional_edges("llm_commentary", tools_condition, {"tools": "tools", END: "extract_commentary"})
    builder.add_edge("extract_commentary", "prepare_move_analysis")

    builder.add_edge("prepare_move_analysis", "llm_analysis")
    builder.add_conditional_edges("llm_analysis", tools_condition, {"tools": "tools", END: "extract_move_analysis"})
    builder.add_edge("extract_move_analysis", "llm_move_extract")

    builder.add_conditional_edges("llm_move_extract", tools_condition, {"tools": "tools", END: "extract_next_move"})
    builder.add_conditional_edges("extract_next_move", _route_after_validate, {
        "prepare_move_retry": "prepare_move_retry",
        "prepare_message": "prepare_message",
    })

    builder.add_edge("prepare_move_retry", "llm_retry")
    builder.add_conditional_edges("llm_retry", tools_condition, {"tools": "tools", END: "extract_move_retry"})
    builder.add_edge("extract_move_retry", "llm_retry_extract")

    builder.add_conditional_edges("llm_retry_extract", tools_condition, {"tools": "tools", END: "extract_retry_move"})
    builder.add_conditional_edges("extract_retry_move", _route_after_validate, {
        "prepare_move_retry": "prepare_move_retry",
        "prepare_message": "prepare_message",
    })

    builder.add_edge("prepare_message", "llm_message")
    builder.add_conditional_edges("llm_message", tools_condition, {"tools": "tools", END: "extract_message"})
    builder.add_edge("extract_message", END)

    builder.add_conditional_edges("tools", _route_tools_back)

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
    store_uri: str,
    legal_moves: list[str] | None = None,
    white: str | None = None,
) -> MoveState:
    tool_provider = ToolProvider(game_service=game_svc, game_session_id=game_session_id)
    try:
        tools = tool_provider.get_tools() + [SCORE_OUTPUT_TOOL, NEXT_MOVE_OUTPUT_TOOL]
        mw = MoveWorkflow(llm, game_svc, tool_provider, tools=tools)

        async with AsyncPostgresStore.from_conn_string(store_uri) as store:
            await store.setup()
            graph = build_move_workflow(mw).compile(store=store)

            initial = MoveState(
                fen=fen,
                move=move,
                user_id=user_id,
                username=username,
                level=level,
                game_session_id=game_session_id,
                legal_moves=legal_moves or [],
                white=white or "student",
            )

            result = await asyncio.shield(graph.ainvoke(initial, context=MoveContext(game_session_id=game_session_id)))

        return MoveState(**result)
    finally:
        tool_provider.close()

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated
from uuid import UUID

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from core.game.models import Event, EventRole, EventType
from core.agent.models import LLMClient
from core.agent.prompts import PromptGetter
from core.agent.token_tracker import log_token_usage, token_totals
from core.game.tools import ToolProvider

logger = logging.getLogger(__name__)


@dataclass
class QueryState:
    query: str = ""
    fen: str = ""
    white: str = "student"
    game_session_id: str = ""
    user_id: str = ""
    username: str = ""
    level: int = 1
    explanation: str = ""

    messages: Annotated[list[BaseMessage], add_messages] = field(default_factory=list)
    _current_step: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> QueryState:
        return cls(
            query=data.get("query", ""),
            fen=data.get("fen", ""),
            white=data.get("white", "student"),
            game_session_id=data.get("game_session_id", ""),
            user_id=data.get("user_id", ""),
            username=data.get("username", ""),
            level=data.get("level", 1),
            explanation=data.get("explanation", ""),
        )


QUERY_PROMPT = """
FEN: {fen}
Student: {username}
You (Vishy) are playing as {vishy_color}. The student is {student_color}.

Student query: {query}
"""


def _player_colors(white: str) -> tuple[str, str]:
    if white == "instructor":
        return ("white", "black")
    return ("black", "white")


class QueryWorkflow:
    def __init__(
        self,
        llm: LLMClient,
        game_svc,
        tool_provider: ToolProvider,
        tools: Sequence[BaseTool],
        token_persist: Callable[[str, int, int], Awaitable[None]],
    ) -> None:
        self._llm = llm
        self._game_svc = game_svc
        self._tool_provider = tool_provider
        self._tools = tools
        self._llm_with_tools = llm.bind_tools(list(self._tools))
        self._token_persist = token_persist

    def _build_messages(self, system_content: str, *, no_tool: bool = False) -> list[BaseMessage]:
        if no_tool:
            system_content = system_content.rstrip() + "\n\nNO_TOOL"
        return [HumanMessage(content=system_content)]

    async def _prepare_query(self, state: QueryState) -> dict:
        vishy_color, student_color = _player_colors(state.white)

        events = await self._game_svc.get_events(
            UUID(state.game_session_id),
            event_types=["move", "explain", "query"],
            limit=10,
        )

        prompt = QUERY_PROMPT.format(
            fen=state.fen,
            username=state.username,
            query=state.query,
            vishy_color=vishy_color,
            student_color=student_color,
        )
        messages: list[BaseMessage] = []
        if events:
            for e in reversed(events):
                role = "Vishy" if e.role == EventRole.INSTRUCTOR else "Student"
                content = f"[{role}] [{e.event_type.value}] {e.payload}"
                messages.append(HumanMessage(content=content))
        messages.append(HumanMessage(content=prompt))
        return {"messages": messages, "_current_step": "query"}

    async def _extract_explanation(self, state: QueryState) -> dict:
        if state.messages:
            last_msg = str(getattr(state.messages[-1], "text", "") or "")
        else:
            last_msg = ""

        if state.game_session_id:
            try:
                await self._game_svc.add_event(Event(
                    game_session_id=UUID(state.game_session_id),
                    user_id=UUID(state.user_id),
                    role=EventRole.STUDENT,
                    event_type=EventType.QUERY,
                    metadata={"query": state.query},
                ))
            except Exception:
                logger.exception("failed to record student query event")
            try:
                await self._game_svc.add_event(Event(
                    game_session_id=UUID(state.game_session_id),
                    user_id=UUID(state.user_id),
                    role=EventRole.INSTRUCTOR,
                    event_type=EventType.EXPLAIN,
                    metadata={"message": last_msg},
                ))
            except Exception:
                logger.exception("failed to record instructor explain event")

        return {"explanation": last_msg, "_current_step": "done"}

    def _make_llm_node(self, step: str):
        async def node(state: QueryState) -> dict:
            logger.info("QUERY CONTEXT HAS %d messages", len(state.messages))
            response = await self._llm_with_tools.ainvoke(state.messages)
            usage = getattr(response, "usage_metadata", None)
            log_token_usage(f"llm_{step}", usage)
            if state.game_session_id:
                i, o = token_totals(usage)
                await self._token_persist(state.game_session_id, i, o)
            return {"messages": [response], "_current_step": step}
        return node


def _route_tools_back(state: QueryState) -> str:
    mapping = {
        "query": "llm_query",
    }
    return mapping.get(state._current_step, END)


def _inject_system_prompt(state: QueryState) -> dict:
    prompt = PromptGetter().main_prompt()
    if prompt:
        return {"messages": [SystemMessage(content=prompt)]}
    return {}


def build_query_workflow(qw: QueryWorkflow) -> StateGraph:
    builder = StateGraph(QueryState)

    builder.add_node("start", _inject_system_prompt)
    builder.add_node("prepare_query", qw._prepare_query)
    builder.add_node("llm_query", qw._make_llm_node("query"))
    builder.add_node("extract_explanation", qw._extract_explanation)
    builder.add_node("tools", ToolNode(qw._tools))

    builder.set_entry_point("start")
    builder.add_edge("start", "prepare_query")
    builder.add_edge("prepare_query", "llm_query")
    builder.add_conditional_edges("llm_query", tools_condition, {"tools": "tools", END: "extract_explanation"})
    builder.add_edge("extract_explanation", END)
    builder.add_conditional_edges("tools", _route_tools_back)

    return builder


async def run_query_workflow(
    query: str,
    game_session_id: str,
    user_id: str,
    username: str,
    level: int,
    fen: str,
    white: str,
    llm: LLMClient,
    game_svc,
    token_persist: Callable[[str, int, int], Awaitable[None]],
) -> QueryState:
    tool_provider = ToolProvider(game_service=game_svc, game_session_id=game_session_id)
    try:
        query_tools = tool_provider.get_tools()
        qw = QueryWorkflow(llm, game_svc, tool_provider, tools=query_tools, token_persist=token_persist)

        graph = build_query_workflow(qw).compile()
        result = await graph.ainvoke(
            QueryState(
                query=query,
                fen=fen,
                white=white,
                game_session_id=game_session_id,
                user_id=user_id,
                username=username,
                level=level,
            ),
        )
        return QueryState.from_dict(result)
    finally:
        tool_provider.close()

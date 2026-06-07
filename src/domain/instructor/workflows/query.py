from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Annotated, Sequence
from uuid import UUID

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from domain.game.model import Event, EventRole, EventType
from domain.instructor.model import LLMClient
from domain.instructor.prompt import PromptGetter
from domain.toolprovider.service import ToolProvider

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
    def __init__(self, llm: LLMClient, game_svc, tool_provider: ToolProvider, tools: Sequence[BaseTool]) -> None:
        self._llm = llm
        self._game_svc = game_svc
        self._tool_provider = tool_provider
        self._tools = tools
        self._llm_with_tools = llm.bind_tools(list(self._tools))

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
        system = self._system_prompt()
        if system:
            messages.append(SystemMessage(content=system))
        if events:
            for e in reversed(events):
                role = "Vishy" if e.role == EventRole.INSTRUCTOR else "Student"
                content = f"[{role}] [{e.event_type.value}] {e.payload}"
                messages.append(HumanMessage(content=content))
        messages.append(HumanMessage(content=prompt))
        return {"messages": messages, "_current_step": "query"}

    async def _extract_explanation(self, state: QueryState) -> dict:
        if state.messages:
            last_msg = str(getattr(state.messages[-1], "content", "") or "")
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
            return {"messages": [response], "_current_step": step}
        return node


def _route_tools_back(state: QueryState) -> str:
    mapping = {
        "query": "llm_query",
    }
    return mapping.get(state._current_step, END)


def build_query_workflow(qw: QueryWorkflow) -> StateGraph:
    builder = StateGraph(QueryState)

    builder.add_node("start", lambda state: {})
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
) -> QueryState:
    tool_provider = ToolProvider(game_service=game_svc, game_session_id=game_session_id)
    try:
        query_tools = tool_provider.get_tools()
        qw = QueryWorkflow(llm, game_svc, tool_provider, tools=query_tools)

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

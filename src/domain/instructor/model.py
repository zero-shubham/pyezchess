from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable, Literal

from pydantic import BaseModel, Field
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool


class NextMoveOutput(BaseModel):
    move: str = Field(
        description="The chosen move in Standard Algebraic Notation (SAN), e.g. Nf3, e4, O-O")


class MessageOutput(BaseModel):
    message: str = Field(
        description="Explanation to the student about why the instructor chose this move, 2-3 sentences")


class ScoreOutput(BaseModel):
    grade: Literal["STRONG", "GOOD", "WEAK"] = Field(
        description="Quality grade of the student's move"
    )
    delta: Literal[3, 1, 0] = Field(
        description="Score delta: 3 for STRONG, 1 for GOOD, 0 for WEAK"
    )
    reason: str = Field(
        description="Brief explanation of why this grade was assigned"
    )


@runtime_checkable
class LLMClient(Protocol):
    def bind_tools(self, tools: list[BaseTool]) -> Runnable:
        ...

    def with_structured_output(self, schema: type[BaseModel]) -> Runnable:
        ...


@dataclass
class ConversationMessage:
    role: str
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class MovePlayedResult:
    valid: bool = False
    fen: str = ""
    explanation: str = ""
    move: str = ""
    score: int = 0
    score_grade: str = ""
    is_best: bool = False
    commentary: str = ""


MOVE_SIDE = Literal["student", "instructor"]


@dataclass
class ExplainResult:
    explanation: str = ""
    game_session_id: str = ""
    fen: str = ""
    white: MOVE_SIDE = "student"
    instructor_move: str = ""
    captured: dict = field(default_factory=dict)


@dataclass
class HintResult:
    hint: str = ""


class ToolExecutor(Protocol):
    async def execute(self, tool_name: str,
                      arguments: dict[str, Any]) -> dict[str, Any]: ...


class ErrNoActiveSession(Exception):
    pass


class ErrLLMAPIFailed(Exception):
    pass


class ErrInvalidMove(Exception):
    pass

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field


class EvaluateMoveInput(BaseModel):
    fen: str = Field(description="FEN string of the position before the move")
    san_move: str = Field(
        description="Move in SAN notation, e.g. 'e4', 'Nf3', 'O-O'"
    )


class GetSessionHistoryInput(BaseModel):
    limit: int = Field(description="Number of recent events to return")
    event_types: list[str] = Field(
        default=["move"],
        description="Filter by event types: move, hint, explain, move_result, start_game, query. Defaults to ['move'].",
    )


class GetLevelDetailsInput(BaseModel):
    level: int = Field(description="Level number (1-4)")
    topic: str = Field(
        default="", description="Optional topic ID like '1.1', '2.3'"
    )


class GetTopMovesInput(BaseModel):
    fen: str = Field(description="FEN string of the position to analyze")
    n: int = Field(
        default=3,
        description="Number of top moves to return (1-5, defaults to 3)",
    )


class GetCurrentFenInput(BaseModel):
    """No parameters needed — returns the current board FEN."""
    pass


@dataclass(frozen=True)
class TopMove:
    move: str
    score: str


@dataclass(frozen=True)
class ToolError:
    error: str = ""


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_session_history",
            "description": "Returns recent session activity and events",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of recent events to return"},
                    "event_types": {"type": "array", "items": {"type": "string"}, "description": "Filter by event types: move, hint, explain, move_result, start_game, query. Defaults to ['move']."},
                },
                "required": ["limit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "evaluate_move",
            "description": "Evaluates a chess move using Stockfish. Returns pre-move and post-move scores (centipawn or mate depth) for a given FEN position and a SAN move.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fen": {"type": "string", "description": "FEN string of the position before the move"},
                    "san_move": {"type": "string", "description": "Move in SAN notation, e.g. 'e4', 'Nf3', 'O-O'"},
                },
                "required": ["fen", "san_move"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_level_details",
            "description": "Returns curriculum details for a level, or a specific topic within a level",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {"type": "integer", "description": "Level number (1-4)"},
                    "topic": {"type": "string", "description": "Optional topic ID like '1.1', '2.3'"},
                },
                "required": ["level"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_moves",
            "description": "Returns the top N best moves for a given FEN position using Stockfish, with evaluation scores.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fen": {"type": "string", "description": "FEN string of the position to analyze"},
                    "n": {"type": "integer", "description": "Number of top moves to return (1-5, defaults to 3)"},
                },
                "required": ["fen"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_fen",
            "description": "Returns the current board position as a FEN string. Use this to get the latest board status before calling other tools that need a FEN.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


def get_tool_definitions() -> list[dict[str, Any]]:
    return TOOL_SCHEMAS
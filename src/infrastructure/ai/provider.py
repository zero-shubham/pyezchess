from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ProviderType(StrEnum):
    CLAUDE = "claude"
    DEEPSEEK = "deepseek"
    GEMINI = "gemini"
    OPENAI = "openai"


@dataclass
class LLMProvider:
    type: ProviderType
    api_key: str
    model: str = ""

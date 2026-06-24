from core.agent.models import (
    ExplainResult,
    LLMClient,
    MovePlayedResult,
    QueryResult,
)
from core.agent.prompts import PromptGetter
from core.agent.token_tracker import TokenUsageCallback, log_token_usage, token_totals


def __getattr__(name: str):
    if name == "Instructor":
        from core.agent.interfaces import Instructor
        return Instructor
    if name == "LangGraphInstructor":
        from core.agent.services import LangGraphInstructor
        return LangGraphInstructor
    if name == "LLMProvider":
        from core.agent.clients import LLMProvider
        return LLMProvider
    if name == "LLMWrapper":
        from core.agent.clients import LLMWrapper
        return LLMWrapper
    if name == "create_llm_client":
        from core.agent.clients import create_llm_client
        return create_llm_client
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ExplainResult",
    "LLMClient",
    "MovePlayedResult",
    "QueryResult",
    "PromptGetter",
    "TokenUsageCallback",
    "log_token_usage",
    "token_totals",
    "Instructor",
    "LangGraphInstructor",
    "LLMProvider",
    "LLMWrapper",
    "create_llm_client",
]

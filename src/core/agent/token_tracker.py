from __future__ import annotations

import logging
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger(__name__)


def _to_int_or_none(v: Any) -> int | None:
    if isinstance(v, (int, float)):
        return int(v)
    return None


def _safe_int_dict(d: Any) -> dict[str, int]:
    return {str(k): vi for k, v in d.items() if (vi := _to_int_or_none(v)) is not None}


class TokenUsageCallback(BaseCallbackHandler):
    """Callback that captures token usage from a single LLM call.

    Usage:
        cb = TokenUsageCallback()
        result = await runnable.ainvoke(input, config={"callbacks": [cb]})
        tokens = cb.usage_metadata  # dict or None
    """

    def __init__(self) -> None:
        self.usage_metadata: dict[str, int] | None = None

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        llm_output: Any = getattr(response, "llm_output", None) or {}
        token_usage: Any = llm_output.get("token_usage")
        if isinstance(token_usage, dict):
            self.usage_metadata = _safe_int_dict(token_usage)
            return

        generations: Any = getattr(response, "generations", [])
        for gen_list in generations:
            for gen in gen_list:
                msg: Any = getattr(gen, "message", None)
                if msg is None:
                    continue
                um: Any = getattr(msg, "usage_metadata", None)
                if isinstance(um, dict):
                    self.usage_metadata = _safe_int_dict(um)
                    return
                rm: Any = getattr(msg, "response_metadata", None) or {}
                tu: Any = rm.get("token_usage")
                if isinstance(tu, dict):
                    self.usage_metadata = _safe_int_dict(tu)
                    return


def log_token_usage(step: str, usage: dict[str, int] | None) -> None:
    if not usage:
        return
    input_tokens = usage.get("input_tokens") or usage.get("prompt_tokens", 0)
    output_tokens = usage.get("output_tokens") or usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", 0)
    logger.info("Token usage [%s]: input=%d output=%d total=%d",
                 step, input_tokens, output_tokens, total_tokens)


def token_totals(usage: dict[str, int] | None) -> tuple[int, int]:
    if not usage:
        return (0, 0)
    i = usage.get("input_tokens") or usage.get("prompt_tokens", 0)
    o = usage.get("output_tokens") or usage.get("completion_tokens", 0)
    return (i, o)

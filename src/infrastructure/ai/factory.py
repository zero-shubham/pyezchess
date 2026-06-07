from __future__ import annotations

import logging
from typing import Any

from infrastructure.ai.provider import LLMProvider, ProviderType
from pydantic import BaseModel, SecretStr

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


class LLMWrapper:
    def __init__(self, chat_model: BaseChatModel, structured_method: str | None = None) -> None:
        self._chat_model = chat_model
        self._structured_method = structured_method

    def bind_tools(self, tools: list[BaseTool]) -> Runnable:
        return self._chat_model.bind_tools(tools)

    def with_structured_output(self, schema: type[BaseModel]) -> Runnable:
        kwargs: dict[str, Any] = {}
        if self._structured_method is not None:
            kwargs["method"] = self._structured_method
        return self._chat_model.with_structured_output(schema, **kwargs)


def create_llm_client(provider: LLMProvider) -> LLMWrapper:
    if provider.type == ProviderType.CLAUDE:
        chat_model = ChatAnthropic(
            model_name=provider.model or "claude-sonnet-4-20250514",
            api_key=SecretStr(provider.api_key),
            timeout=10,
            stop=None,
        )
        return LLMWrapper(chat_model)
    elif provider.type == ProviderType.DEEPSEEK:
        chat_model = ChatOpenAI(
            model=provider.model or "deepseek-chat",
            api_key=lambda: provider.api_key,
            base_url="https://api.deepseek.com/v1",
        )
        return LLMWrapper(chat_model, structured_method="function_calling")
    else:
        raise ValueError(f"unsupported provider: {provider.type}")

from __future__ import annotations

from typing import Any

from infrastructure.ai.provider import LLMProvider, ProviderType
from pydantic import BaseModel, SecretStr

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool


class LangChainLLMAdapter:
    def __init__(self, chat_model: BaseChatModel, structured_method: str | None = None) -> None:
        self._chat_model = chat_model
        self._structured_method = structured_method

    def bind_tools(self, tools: list[BaseTool]) -> Runnable:
        return self._chat_model.bind_tools(tools)

    async def generate_content(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> dict[str, Any]:
        lc_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "assistant":
                ai_msg = AIMessage(content=content or "")
                tool_calls = msg.get("tool_calls")
                if tool_calls:
                    lc_tool_calls = []
                    for tc in tool_calls:
                        tc_func = tc.get("function", {})
                        lc_tool_calls.append({
                            "name": tc_func.get("name", ""),
                            "args": tc_func.get("arguments", {}),
                            "id": tc.get("id", ""),
                            "type": "tool_call",
                        })
                    ai_msg.tool_calls = lc_tool_calls
                lc_messages.append(ai_msg)
            elif role == "tool":
                lc_messages.append(ToolMessage(
                    content=content,
                    tool_call_id=msg.get("tool_call_id", ""),
                ))
            else:
                lc_messages.append(HumanMessage(content=content))

        kwargs: dict[str, Any] = {}
        if tools:
            kwargs["tools"] = tools

        result = await self._chat_model.ainvoke(lc_messages, **kwargs)

        response: dict[str, Any] = {"text": result.content or ""}
        if hasattr(result, "tool_calls") and result.tool_calls:
            response["tool_calls"] = [
                {
                    "id": tc.get("id", ""),
                    "function": {
                        "name": tc.get("name", ""),
                        "arguments": tc.get("args", {}),
                    },
                }
                for tc in result.tool_calls
            ]
        return response

    async def generate_structured(
        self, messages: list[dict], schema: type[BaseModel]
    ) -> Any:
        lc_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                lc_messages.append(HumanMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))

        kwargs: dict[str, Any] = {}
        if self._structured_method is not None:
            kwargs["method"] = self._structured_method
        structured_model = self._chat_model.with_structured_output(schema, **kwargs)
        return await structured_model.ainvoke(lc_messages)


def create_llm_client(provider: LLMProvider) -> LangChainLLMAdapter:
    if provider.type == ProviderType.CLAUDE:
        chat_model = ChatAnthropic(
            model_name=provider.model or "claude-sonnet-4-20250514",
            api_key=SecretStr(provider.api_key),
            timeout=10,
            stop=None,
        )
        return LangChainLLMAdapter(chat_model)
    elif provider.type == ProviderType.DEEPSEEK:
        chat_model = ChatOpenAI(
            model=provider.model or "deepseek-chat",
            api_key=lambda: provider.api_key,
            base_url="https://api.deepseek.com/v1",
        )
        return LangChainLLMAdapter(chat_model, structured_method="function_calling")
    else:
        raise ValueError(f"unsupported provider: {provider.type}")

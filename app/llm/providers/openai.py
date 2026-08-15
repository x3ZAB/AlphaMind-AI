import json
from typing import Any

import httpx

from app.llm.base import BaseLLMProvider, LLMStepResponse, ToolCall, ToolDefinition
from app.llm.errors import LLMProviderError


class OpenAIProvider(BaseLLMProvider):
    BASE_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("An API key is required")

        if not model:
            raise ValueError("A model is required")

        self._api_key = api_key
        self.model = model
        self._client = client

    def _build_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        formatted: list[dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "user")

            if role == "tool":
                formatted.append({
                    "role": "tool",
                    "tool_call_id": msg.get("call_id") or msg.get("tool_call_id", "call_default"),
                    "name": msg.get("name"),
                    "content": json.dumps(msg.get("content") or msg.get("output", "")),
                })
                continue

            if role == "assistant" and msg.get("tool_calls"):
                raw_calls = msg["tool_calls"]
                formatted_calls = []
                for tc in raw_calls:
                    if isinstance(tc, ToolCall):
                        formatted_calls.append({
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        })
                    elif isinstance(tc, dict):
                        formatted_calls.append({
                            "id": tc.get("id", "call_default"),
                            "type": "function",
                            "function": {
                                "name": tc.get("name"),
                                "arguments": json.dumps(tc.get("arguments", {})),
                            },
                        })

                item: dict[str, Any] = {"role": "assistant", "tool_calls": formatted_calls}
                if msg.get("content"):
                    item["content"] = msg["content"]
                formatted.append(item)
                continue

            formatted.append({
                "role": role,
                "content": msg.get("content", ""),
            })

        return formatted

    async def generate_step(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMStepResponse:
        payload: dict[str, Any] = {
            key: value
            for key, value in kwargs.items()
            if key not in {"model", "messages", "tools"}
        }

        payload["model"] = self.model
        payload["messages"] = self._build_messages(messages)

        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name if isinstance(tool, ToolDefinition) else tool["name"],
                        "description": tool.description if isinstance(tool, ToolDefinition) else tool["description"],
                        "parameters": tool.input_schema if isinstance(tool, ToolDefinition) else tool["input_schema"],
                    },
                }
                for tool in tools
            ]

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            if self._client is None:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.BASE_URL,
                        headers=headers,
                        json=payload,
                    )
            else:
                response = await self._client.post(
                    self.BASE_URL,
                    headers=headers,
                    json=payload,
                )

            response.raise_for_status()
            data = response.json()

        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(
                f"LLM provider returned HTTP {exc.response.status_code}"
            ) from None

        except (httpx.HTTPError, ValueError):
            raise LLMProviderError(
                "LLM provider request failed"
            ) from None

        try:
            choice_msg = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise LLMProviderError(
                "LLM provider returned an invalid response"
            ) from None

        raw_tool_calls = choice_msg.get("tool_calls")
        if raw_tool_calls and isinstance(raw_tool_calls, list):
            parsed_calls: list[ToolCall] = []
            for call in raw_tool_calls:
                fn = call.get("function", {})
                name = fn.get("name")
                args_raw = fn.get("arguments", {})
                if isinstance(args_raw, str):
                    try:
                        args = json.loads(args_raw)
                    except ValueError:
                        args = {}
                else:
                    args = args_raw or {}

                if name:
                    parsed_calls.append(
                        ToolCall(
                            id=call.get("id", f"call_{len(parsed_calls)}"),
                            name=name,
                            arguments=args,
                        )
                    )

            if parsed_calls:
                return LLMStepResponse(
                    content=choice_msg.get("content"),
                    tool_calls=parsed_calls,
                )

        content = choice_msg.get("content")
        if not isinstance(content, str):
            raise LLMProviderError(
                "LLM provider returned a non-text response"
            )

        return LLMStepResponse(content=content.strip(), tool_calls=[])

    async def generate(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        step_response = await self.generate_step(messages, **kwargs)
        if step_response.content is not None:
            return step_response.content
        if step_response.tool_calls:
            return f"Requested tool: {step_response.tool_calls[0].name}"
        return ""
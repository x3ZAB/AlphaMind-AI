import json
import logging
from typing import Any

import httpx

from app.llm.base import BaseLLMProvider, LLMStepResponse, ToolCall, ToolDefinition
from app.llm.errors import LLMProviderError

logger = logging.getLogger(__name__)


def _sanitize_log_data(data: Any) -> Any:
    """Sanitize sensitive data like API keys, tokens, etc."""
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            if k.lower() in {"api_key", "apikey", "token", "authorization", "secret", "password", "x-goog-api-key"}:
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = _sanitize_log_data(v)
        return sanitized
    elif isinstance(data, list):
        return [_sanitize_log_data(item) for item in data]
    elif isinstance(data, str):
        if len(data) > 2000:
            return data[:2000] + "...[TRUNCATED]"
        return data
    return data


class GeminiProvider(BaseLLMProvider):
    BASE_URL = (
        "https://generativelanguage.googleapis.com/v1beta/interactions"
    )

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

    @staticmethod
    def _build_payload(
        messages: list[dict[str, Any]],
        *,
        model: str,
        tools: list[ToolDefinition] | None = None,
        interaction_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        prev_id = interaction_id or kwargs.get("previous_interaction_id")

        if prev_id:
            input_steps: list[dict[str, Any]] = []
            for message in reversed(messages):
                role = message.get("role")
                if role == "tool":
                    tool_name = message.get("name")
                    tool_output = message.get("content") or message.get("output")
                    call_id = message.get("call_id") or message.get("tool_call_id")
                    if isinstance(tool_output, dict):
                        result_text = json.dumps(tool_output)
                    elif isinstance(tool_output, str):
                        result_text = tool_output
                    else:
                        result_text = str(tool_output) if tool_output is not None else ""
                    step: dict[str, Any] = {
                        "type": "function_result",
                        "name": tool_name,
                        "result": [{"type": "text", "text": result_text}],
                    }
                    if call_id:
                        step["call_id"] = call_id
                    input_steps.insert(0, step)
                elif role in {"assistant", "user"}:
                    if input_steps:
                        break
                    if role == "user":
                        content = message.get("content")
                        if content:
                            input_steps.append({
                                "type": "user_input",
                                "content": content,
                            })
                        break

            payload: dict[str, Any] = {
                "model": model,
                "previous_interaction_id": prev_id,
                "input": input_steps,
            }
            return payload

        # Check if messages contain history beyond system/user
        has_history = any(
            m.get("role") in {"assistant", "tool"} for m in messages
        )

        if has_history:
            system_parts: list[str] = []
            input_steps: list[dict[str, Any]] = []

            for message in messages:
                role = message.get("role", "user")
                content = message.get("content")

                if role == "system":
                    if content:
                        system_parts.append(content)
                    continue

                if role == "user":
                    if content:
                        input_steps.append({
                            "type": "user_input",
                            "content": content,
                        })
                    continue

                if role == "assistant":
                    if content:
                        input_steps.append({
                            "type": "model_output",
                            "content": [{"type": "text", "text": content}],
                        })

                    tool_calls = message.get("tool_calls", [])
                    for tc in tool_calls:
                        tc_name = tc.name if isinstance(tc, ToolCall) else tc.get("name")
                        tc_args = tc.arguments if isinstance(tc, ToolCall) else tc.get("arguments", {})
                        tc_id = tc.id if isinstance(tc, ToolCall) else tc.get("id")
                        if tc_name:
                            step = {
                                "type": "function_call",
                                "name": tc_name,
                                "arguments": tc_args,
                            }
                            if tc_id:
                                step["id"] = tc_id
                            input_steps.append(step)
                    continue

                if role == "tool":
                    tool_name = message.get("name")
                    tool_output = message.get("content") or message.get("output")
                    call_id = message.get("call_id") or message.get("tool_call_id")
                    if isinstance(tool_output, dict):
                        result_text = json.dumps(tool_output)
                    elif isinstance(tool_output, str):
                        result_text = tool_output
                    else:
                        result_text = str(tool_output) if tool_output is not None else ""
                    step: dict[str, Any] = {
                        "type": "function_result",
                        "name": tool_name,
                        "result": [{"type": "text", "text": result_text}],
                    }
                    if call_id:
                        step["call_id"] = call_id
                    input_steps.append(step)
                    continue

            payload: dict[str, Any] = {
                "model": model,
                "store": True,
            }

            if system_parts:
                payload["system_instruction"] = "\n\n".join(system_parts)

            if (
                len(input_steps) == 1
                and input_steps[0].get("type") == "user_input"
                and isinstance(input_steps[0].get("content"), str)
            ):
                payload["input"] = input_steps[0]["content"]
            else:
                payload["input"] = input_steps

            if tools:
                formatted_tools: list[dict[str, Any]] = []
                for tool in tools:
                    if isinstance(tool, ToolDefinition):
                        formatted_tools.append({
                            "type": "function",
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.input_schema,
                        })
                    elif isinstance(tool, dict):
                        t = dict(tool)
                        if "type" not in t:
                            t["type"] = "function"
                        formatted_tools.append(t)

                if formatted_tools:
                    payload["tools"] = formatted_tools

            for key, value in kwargs.items():
                if key not in payload and key not in {"model", "messages", "tools", "interaction_id", "previous_interaction_id"}:
                    payload[key] = value

            return payload

        system_parts: list[str] = []
        user_content: str | None = None

        for message in messages:
            role = message.get("role", "user")
            content = message.get("content")

            if role == "system":
                if content:
                    system_parts.append(content)
                continue

            if role == "user":
                if content:
                    user_content = content
                continue

        payload: dict[str, Any] = {
            "model": model,
            "store": True,
        }

        if system_parts:
            payload["system_instruction"] = "\n\n".join(system_parts)

        if user_content:
            payload["input"] = user_content

        if tools:
            formatted_tools: list[dict[str, Any]] = []
            for tool in tools:
                if isinstance(tool, ToolDefinition):
                    formatted_tools.append({
                        "type": "function",
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    })
                elif isinstance(tool, dict):
                    t = dict(tool)
                    if "type" not in t:
                        t["type"] = "function"
                    formatted_tools.append(t)

            if formatted_tools:
                payload["tools"] = formatted_tools

        for key, value in kwargs.items():
            if key not in payload and key not in {"model", "messages", "tools", "interaction_id", "previous_interaction_id"}:
                payload[key] = value

        return payload

    @staticmethod
    def _extract_text(
        data: dict[str, Any],
    ) -> str | None:
        output_text = data.get("output_text")

        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        steps = data.get("steps")

        if not isinstance(steps, list):
            return None

        for step in steps:
            if not isinstance(step, dict):
                continue

            if step.get("type") != "model_output":
                continue

            content_items = step.get("content", [])

            if not isinstance(content_items, list):
                continue

            for content in content_items:
                if not isinstance(content, dict):
                    continue

                if content.get("type") != "text":
                    continue

                text = content.get("text")

                if isinstance(text, str) and text.strip():
                    return text.strip()

        return None

    @staticmethod
    def _extract_tool_calls(data: dict[str, Any]) -> list[ToolCall]:
        tool_calls: list[ToolCall] = []

        steps = data.get("steps")
        if isinstance(steps, list):
            for idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue

                # Interactions API flat format: step with type=function_call
                step_type = step.get("type")
                if step_type in {"function_call", "functionCall"}:
                    name = step.get("name")
                    args = step.get("args") or step.get("arguments") or {}
                    call_id = step.get("id") or step.get("call_id") or f"call_gemini_{idx}_{len(tool_calls)}"
                    if name:
                        tool_calls.append(
                            ToolCall(
                                id=call_id,
                                name=name,
                                arguments=args if isinstance(args, dict) else {},
                            )
                        )
                    continue

                # Legacy nested format: model_output > content[] > function_call
                content_items = step.get("content", [])
                if not isinstance(content_items, list):
                    continue
                for item in content_items:
                    if not isinstance(item, dict):
                        continue
                    item_type = item.get("type")
                    if item_type in {"function_call", "functionCall"}:
                        name = item.get("name") or item.get("functionCall", {}).get("name")
                        args = item.get("args") or item.get("arguments") or item.get("functionCall", {}).get("args") or {}
                        call_id = item.get("id") or item.get("call_id") or f"call_gemini_{idx}_{len(tool_calls)}"
                        if name:
                            tool_calls.append(
                                ToolCall(
                                    id=call_id,
                                    name=name,
                                    arguments=args if isinstance(args, dict) else {},
                                )
                            )

        fc = data.get("function_call") or data.get("functionCall")
        if isinstance(fc, dict) and fc.get("name"):
            args = fc.get("args") or fc.get("arguments") or {}
            call_id = fc.get("id") or fc.get("call_id") or f"call_gemini_root_{len(tool_calls)}"
            tool_calls.append(
                ToolCall(
                    id=call_id,
                    name=fc["name"],
                    arguments=args if isinstance(args, dict) else {},
                )
            )

        return tool_calls

    @staticmethod
    def _safe_error_message(
        response: httpx.Response,
    ) -> str:
        try:
            data = response.json()
        except ValueError:
            text = response.text.strip()

            if not text:
                return "Empty provider error response"

            return text[:500]

        if isinstance(data, dict):
            error = data.get("error")

            if isinstance(error, dict):
                message = error.get("message")

                if isinstance(message, str) and message.strip():
                    return message.strip()[:500]

            message = data.get("message")

            if isinstance(message, str) and message.strip():
                return message.strip()[:500]

        return "Provider returned an error response"

    async def generate_step(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        interaction_id: str | None = None,
        **kwargs: Any,
    ) -> LLMStepResponse:
        headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }

        payload = self._build_payload(
            messages,
            model=self.model,
            tools=tools,
            interaction_id=interaction_id,
            **kwargs,
        )

        sanitized_payload = _sanitize_log_data(payload)
        logger.info(
            "Gemini API Request: URL=%s | Body=%s",
            self.BASE_URL,
            json.dumps(sanitized_payload),
        )

        try:
            if self._client is None:
                async with httpx.AsyncClient(timeout=60.0) as client:
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

            logger.info(
                "Gemini API Response: Status=%d | Body=%s",
                response.status_code,
                _sanitize_log_data(response.text[:2000]),
            )

            if response.is_error:
                status_code = response.status_code
                provider_message = self._safe_error_message(response)
                logger.error(
                    "Gemini API error HTTP %d: %s | Full response: %s",
                    status_code,
                    provider_message,
                    response.text[:1000],
                )

                raise LLMProviderError(
                    "Gemini API returned "
                    f"HTTP {status_code}: "
                    f"{provider_message}"
                )

            try:
                data = response.json()
            except ValueError as exc:
                raise LLMProviderError(
                    "Gemini API returned invalid JSON"
                ) from exc

        except LLMProviderError:
            raise

        except httpx.TimeoutException as exc:
            raise LLMProviderError(
                "Gemini API request timed out"
            ) from exc

        except httpx.NetworkError as exc:
            raise LLMProviderError(
                "Gemini API network request failed"
            ) from exc

        except httpx.HTTPError as exc:
            raise LLMProviderError(
                "Gemini API HTTP request failed"
            ) from exc

        resp_interaction_id = data.get("id") or interaction_id or kwargs.get("previous_interaction_id")

        tool_calls = self._extract_tool_calls(data)
        if tool_calls:
            return LLMStepResponse(content=None, tool_calls=tool_calls, interaction_id=resp_interaction_id)

        text = self._extract_text(data)

        if text is not None:
            return LLMStepResponse(content=text, tool_calls=[], interaction_id=resp_interaction_id)

        status = data.get("status")

        if status == "failed":
            error = data.get("error")

            if isinstance(error, dict):
                message = error.get("message")

                if isinstance(message, str) and message.strip():
                    raise LLMProviderError(
                        "Gemini interaction failed: "
                        f"{message.strip()[:500]}"
                    )

            raise LLMProviderError(
                "Gemini interaction failed"
            )

        raise LLMProviderError(
            "Gemini API returned an invalid response without text output"
        )

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
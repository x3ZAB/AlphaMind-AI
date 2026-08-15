from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    call_id: str
    name: str
    output: Any
    error: str | None = None


@dataclass
class LLMStepResponse:
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    interaction_id: str | None = None


class BaseLLMProvider(ABC):

    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        ...

    async def generate_step(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        interaction_id: str | None = None,
        **kwargs: Any,
    ) -> LLMStepResponse:
        """
        Execute one step of LLM generation with optional tool definitions.
        Returns an LLMStepResponse containing either text content or structured tool calls.
        """
        content = await self.generate(messages, **kwargs)
        return LLMStepResponse(content=content, tool_calls=[])

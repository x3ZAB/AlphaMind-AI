from typing import Any

from app.llm.base import BaseLLMProvider, LLMStepResponse, ToolDefinition


class LLMManager:

    def __init__(self, provider: BaseLLMProvider):
        self.provider = provider

    async def generate(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        return await self.provider.generate(messages, **kwargs)

    async def generate_step(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        interaction_id: str | None = None,
        **kwargs: Any,
    ) -> LLMStepResponse:
        return await self.provider.generate_step(
            messages,
            tools=tools,
            interaction_id=interaction_id,
            **kwargs,
        )

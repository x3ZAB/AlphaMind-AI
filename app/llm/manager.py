from app.llm.base import BaseLLMProvider


class LLMManager:

    def __init__(self, provider: BaseLLMProvider):
        self.provider = provider

    async def generate(
        self,
        messages: list[dict[str, str]],
        **kwargs,
    ) -> str:
        return await self.provider.generate(messages, **kwargs)

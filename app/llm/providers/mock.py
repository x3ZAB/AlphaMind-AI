from app.llm.base import BaseLLMProvider


class MockLLMProvider(BaseLLMProvider):

    async def generate(
        self,
        messages: list[dict[str, str]],
        **kwargs,
    ) -> str:
        return "Mock LLM response"

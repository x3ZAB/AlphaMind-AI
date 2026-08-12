import asyncio

from app.llm.base import BaseLLMProvider
from app.llm.manager import LLMManager
from app.llm.providers.mock import MockLLMProvider


async def test_mock_llm_flow() -> None:
    provider = MockLLMProvider()
    assert isinstance(provider, BaseLLMProvider)

    manager = LLMManager(provider)
    response = await manager.generate(
        [{"role": "user", "content": "Hello"}]
    )

    assert isinstance(response, str)
    assert response == "Mock LLM response"


if __name__ == "__main__":
    asyncio.run(test_mock_llm_flow())
    print("Mock LLM flow test passed")

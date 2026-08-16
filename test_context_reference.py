import asyncio
from types import SimpleNamespace
from typing import Any

from app.agent.agent import AIAgent
from app.llm.base import BaseLLMProvider, LLMStepResponse, ToolCall, ToolDefinition
from app.models.llm_configuration import UserLLMConfiguration
from app.providers.base import BaseProvider
from app.services.conversation_context import ConversationContextManager, context_manager
from app.services.telegram_analysis import TelegramAnalysisService
from app.tools.registry import ToolRegistry
from app.tools.stock import GetCompanyTool, GetStockPriceTool, SearchCompanyTool


class MockProvider(BaseProvider):
    async def get_company(self, ticker: str) -> dict:
        return {
            "name": f"{ticker.upper()} Corporation",
            "ticker": ticker.upper(),
            "finnhubIndustry": "Technology",
            "marketCapitalization": 150000.0,
            "shareOutstanding": 1000.0,
        }

    async def get_stock_price(self, ticker: str) -> dict:
        if ticker.upper() == "FAIL":
            raise RuntimeError("API fetch failed")
        return {
            "c": 141.98,
            "d": 0.58,
            "dp": 0.41,
            "h": 142.50,
            "l": 140.73,
            "o": 141.05,
            "pc": 141.40,
        }

    async def search_company(self, query: str) -> dict:
        return {"result": [{"symbol": query.upper(), "description": f"{query} Corporation"}]}


class SemanticTrackingLLMProvider(BaseLLMProvider):
    def __init__(self) -> None:
        self.received_messages: list[list[dict[str, Any]]] = []

    async def generate(
        self,
        configuration: Any,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        self.received_messages.append(messages)
        return "Analysis generated"

    async def generate_step(
        self,
        configuration: Any,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        interaction_id: str | None = None,
        **kwargs: Any,
    ) -> LLMStepResponse:
        self.received_messages.append(messages)
        system_content = messages[0]["content"] if messages else ""
        user_input = messages[-1]["content"] if len(messages) > 1 else ""

        # Respond appropriately reflecting context understanding
        return LLMStepResponse(
            content=f"Processed query '{user_input}' with context context block: {system_content[:100]}...",
            tool_calls=[]
        )


class FakeConfiguredService:
    def __init__(self, provider: BaseLLMProvider) -> None:
        self.provider = provider

    async def generate_step(
        self,
        configuration: Any,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        interaction_id: str | None = None,
        **kwargs: Any,
    ) -> LLMStepResponse:
        return await self.provider.generate_step(
            configuration,
            messages,
            tools=tools,
            interaction_id=interaction_id,
            **kwargs,
        )


async def test_semantic_context_injection() -> None:
    session_key = "test_user_semantic"
    context_manager.reset_context(session_key)

    provider = SemanticTrackingLLMProvider()
    service = FakeConfiguredService(provider)
    tool_registry = ToolRegistry([
        GetStockPriceTool(provider=MockProvider()),
        GetCompanyTool(provider=MockProvider()),
    ])

    telegram_service = TelegramAnalysisService(
        stock_service=None,
        llm_service=service,
        analysis_service=None,
        tool_registry=tool_registry,
    )

    user = SimpleNamespace(
        id=101,
        telegram_id="101",
        llm_configuration=UserLLMConfiguration(provider="gemini", model="gemini-3.1-flash-lite", encrypted_api_key="key"),
    )

    # 1. First turn: Analyze AAPL
    await telegram_service.analyze(user, "Analyze AAPL")
    ctx1 = context_manager.get_context("101")
    assert ctx1.active_ticker == "AAPL"

    # 2. Second turn: Multiple natural phrasings for follow-up on active stock (without keyword matching)
    phrasings = [
        "Would you buy it at this price?",
        "What are the key risks facing the company?",
        "How risky is that?",
        "Tell me more about its financial health",
    ]
    for phrasing in phrasings:
        await telegram_service.analyze(user, phrasing)
        last_messages = provider.received_messages[-1]
        system_prompt = last_messages[0]["content"]
        assert "Active Stock: AAPL" in system_prompt
        assert "[CONVERSATION CONTEXT & HISTORY]" in system_prompt

    # 3. Third turn: Arbitrary comparison pair (PLTR and RKLB)
    await telegram_service.analyze(user, "Compare PLTR and RKLB")
    ctx3 = context_manager.get_context("101")
    assert ctx3.comparison_pair == ["PLTR", "RKLB"]

    # 4. Fourth turn: Multiple natural phrasings for comparison follow-up
    comparison_phrasings = [
        "Which one is better?",
        "Which company looks stronger?",
        "Who has the better outlook?",
        "Which would you prefer?",
    ]
    for phrasing in comparison_phrasings:
        await telegram_service.analyze(user, phrasing)
        last_messages = provider.received_messages[-1]
        system_prompt = last_messages[0]["content"]
        assert "PLTR" in system_prompt
        assert "RKLB" in system_prompt
        assert "[CONVERSATION CONTEXT & HISTORY]" in system_prompt


async def test_tool_failure_reporting() -> None:
    tool_registry = ToolRegistry([
        GetStockPriceTool(provider=MockProvider()),
    ])

    result = await tool_registry.execute("get_stock_price", {"ticker": "FAIL"})
    assert "error" in result
    assert "API fetch failed" in result["error"]


async def test_conversational_references_suite() -> None:
    # Verify conversational references are NEVER extracted as standalone tickers by extract_tickers_from_text
    conversational_phrases = [
        "buy it with $3024?",
        "is the first one better?",
        "is the second one better?",
        "Why is it up?",
        "Should I buy it?",
        "this stock",
        "this company",
        "that stock",
        "tell me more about the first company",
        "tell me more about the second company",
        "compare them",
        "which company looks stronger?",
        "who has the better outlook?",
    ]
    for phrase in conversational_phrases:
        assert context_manager.extract_tickers_from_text(phrase) == [], f"Conversational phrase '{phrase}' extracted invalid ticker!"


def main() -> None:
    asyncio.run(test_semantic_context_injection())
    asyncio.run(test_tool_failure_reporting())
    asyncio.run(test_conversational_references_suite())
    print("Conversation context & reference resolution tests passed successfully!")


if __name__ == "__main__":
    main()

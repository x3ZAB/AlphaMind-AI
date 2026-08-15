import asyncio
import json
from types import SimpleNamespace
from typing import Any

import httpx

from app.agent.agent import MAX_TOOL_CALL_ROUNDS, AIAgent
from app.llm.base import BaseLLMProvider, LLMStepResponse, ToolCall, ToolDefinition
from app.llm.providers.gemini import GeminiProvider
from app.llm.providers.openai import OpenAIProvider
from app.llm.service import ConfiguredLLMService
from app.models.llm_configuration import UserLLMConfiguration
from app.providers.base import BaseProvider
from app.services.telegram_analysis import TelegramAnalysisService
from app.tools.base import Tool
from app.tools.registry import ToolRegistry
from app.tools.stock import GetCompanyTool, GetStockPriceTool, SearchCompanyTool


class FakeFinnhubProvider(BaseProvider):
    async def get_company(self, ticker: str) -> dict:
        if ticker.upper() == "FAIL":
            raise RuntimeError("API error")
        return {
            "name": "NVIDIA Corporation",
            "ticker": ticker.upper(),
            "finnhubIndustry": "Semiconductors",
            "marketCapitalization": 2500000.0,
            "shareOutstanding": 2400.0,
        }

    async def get_stock_price(self, ticker: str) -> dict:
        if ticker.upper() == "FAIL":
            raise RuntimeError("API error")
        return {
            "c": 125.5,
            "d": 2.5,
            "dp": 2.03,
            "h": 126.0,
            "l": 123.0,
            "o": 123.5,
            "pc": 123.0,
        }

    async def get_stock_candles(self, ticker: str, lookback_days: int = 60) -> list[dict]:
        if ticker.upper() == "NOCANDLES":
            import httpx
            req = httpx.Request("GET", "https://finnhub.io/api/v1/stock/candle")
            res = httpx.Response(403, json={"error": "access_denied"}, request=req)
            raise httpx.HTTPStatusError("403 Forbidden", request=req, response=res)
        base_time = 1767225600
        return [
            {"t": base_time + i * 86400, "o": 100.0 + i, "h": 102.0 + i, "l": 99.0 + i, "c": 101.0 + i, "v": 1000}
            for i in range(lookback_days)
        ]

    async def search_company(self, query: str) -> dict:
        if query.upper() == "FAIL":
            raise RuntimeError("Search failed")
        return {
            "result": [
                {
                    "symbol": "AAPL",
                    "description": "Apple Inc",
                    "displaySymbol": "AAPL",
                }
            ]
        }


# --- Tool tests -------------------------------------------------------------


async def test_get_stock_price_tool() -> None:
    tool = GetStockPriceTool(provider=FakeFinnhubProvider())
    result = await tool.execute({"ticker": "nvda"})
    assert result["ticker"] == "NVDA"
    assert result["price"] == 125.5
    assert result["change"] == 2.5
    assert "context" in result
    assert "sma20" in result["context"]["metrics"]
    assert "sma50" in result["context"]["metrics"]
    assert result["context"]["historical"]["available"] is True

    # Test historical access_denied graceful fallback
    no_candles = await tool.execute({"ticker": "nocandles"})
    assert no_candles["context"]["historical"]["available"] is False
    assert no_candles["context"]["historical"]["reason"] == "access_denied"

    missing = await tool.execute({})
    assert "error" in missing

    failed = await tool.execute({"ticker": "fail"})
    assert "error" in failed


async def test_get_company_tool() -> None:
    tool = GetCompanyTool(provider=FakeFinnhubProvider())
    result = await tool.execute({"ticker": "nvda"})
    assert result["ticker"] == "NVDA"
    assert result["name"] == "NVIDIA Corporation"
    assert result["industry"] == "Semiconductors"

    missing = await tool.execute({})
    assert "error" in missing

    failed = await tool.execute({"ticker": "fail"})
    assert "error" in failed


async def test_search_company_tool() -> None:
    tool = SearchCompanyTool(provider=FakeFinnhubProvider())
    result = await tool.execute({"query": "Apple"})
    assert result["query"] == "Apple"
    assert result["ticker"] == "AAPL"
    assert result["name"] == "Apple Inc"

    missing = await tool.execute({})
    assert "error" in missing

    failed = await tool.execute({"query": "fail"})
    assert "error" in failed


# --- Registry tests ---------------------------------------------------------


def test_tool_registry() -> None:
    registry = ToolRegistry()
    assert registry.get("get_stock_price") is not None
    assert registry.get("get_company") is not None
    assert registry.get("search_company") is not None
    assert len(registry.list_tools()) == 3
    assert len(registry.get_definitions()) == 3

    unknown = registry.get("nonexistent")
    assert unknown is None


async def test_registry_execution_and_validation() -> None:
    registry = ToolRegistry()
    unknown_res = await registry.execute("nonexistent", {"ticker": "NVDA"})
    assert "Unknown tool" in unknown_res["error"]

    missing_param = await registry.execute("get_stock_price", {})
    assert "Missing required parameter" in missing_param["error"]


# --- Mock LLM for Agent tests -----------------------------------------------


class ScriptedLLMProvider(BaseLLMProvider):
    def __init__(self, steps: list[LLMStepResponse]) -> None:
        self.steps = steps
        self.current_step = 0
        self.received_messages: list[list[dict[str, Any]]] = []

    async def generate(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        step = await self.generate_step(messages, **kwargs)
        return step.content or ""

    async def generate_step(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMStepResponse:
        self.received_messages.append(messages)
        if self.current_step < len(self.steps):
            response = self.steps[self.current_step]
            self.current_step += 1
            return response
        return LLMStepResponse(content="Final step fallback", tool_calls=[])


class FakeConfiguredService(ConfiguredLLMService):
    def __init__(self, provider: BaseLLMProvider) -> None:
        self.provider = provider
        super().__init__()

    async def generate_step(
        self,
        configuration: UserLLMConfiguration,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMStepResponse:
        return await self.provider.generate_step(messages, tools=tools, **kwargs)


# --- Agent tests ------------------------------------------------------------


async def test_agent_returns_final_text_directly() -> None:
    provider = ScriptedLLMProvider([
        LLMStepResponse(content="NVIDIA is doing well.", tool_calls=[])
    ])
    service = FakeConfiguredService(provider)
    agent = AIAgent(llm_service=service)
    config = UserLLMConfiguration(provider="gemini", model="gemini-3.1-flash-lite", encrypted_api_key="key")

    result = await agent.run(config, "How is NVIDIA doing?")
    assert result == "NVIDIA is doing well."
    assert len(provider.received_messages) == 1


async def test_agent_executes_single_tool_and_returns_final_text() -> None:
    provider = ScriptedLLMProvider([
        LLMStepResponse(
            content=None,
            tool_calls=[ToolCall(id="call_1", name="get_stock_price", arguments={"ticker": "NVDA"})],
        ),
        LLMStepResponse(content="NVIDIA (NVDA) price is $125.50.", tool_calls=[]),
    ])
    service = FakeConfiguredService(provider)
    tool_registry = ToolRegistry([GetStockPriceTool(provider=FakeFinnhubProvider())])
    agent = AIAgent(llm_service=service, tool_registry=tool_registry)
    config = UserLLMConfiguration(provider="gemini", model="gemini-3.1-flash-lite", encrypted_api_key="key")

    result = await agent.run(config, "What's NVDA price?")
    assert "NVIDIA (NVDA) price is $125.50." in result
    assert len(provider.received_messages) == 2

    # Verify second turn contained tool output
    second_turn_messages = provider.received_messages[1]
    tool_msg = next(m for m in second_turn_messages if m.get("role") == "tool")
    assert tool_msg["name"] == "get_stock_price"
    assert tool_msg["content"]["price"] == 125.5


async def test_agent_executes_multi_step_sequential_tools() -> None:
    provider = ScriptedLLMProvider([
        # Step 1: Search for company
        LLMStepResponse(
            content=None,
            tool_calls=[ToolCall(id="call_1", name="search_company", arguments={"query": "Apple"})],
        ),
        # Step 2: Get company details & price
        LLMStepResponse(
            content=None,
            tool_calls=[
                ToolCall(id="call_2", name="get_company", arguments={"ticker": "AAPL"}),
                ToolCall(id="call_3", name="get_stock_price", arguments={"ticker": "AAPL"}),
            ],
        ),
        # Step 3: Final answer
        LLMStepResponse(content="Apple Inc (AAPL) is trading at $125.50.", tool_calls=[]),
    ])
    service = FakeConfiguredService(provider)
    tool_registry = ToolRegistry([
        GetStockPriceTool(provider=FakeFinnhubProvider()),
        GetCompanyTool(provider=FakeFinnhubProvider()),
        SearchCompanyTool(provider=FakeFinnhubProvider()),
    ])
    agent = AIAgent(llm_service=service, tool_registry=tool_registry)
    config = UserLLMConfiguration(provider="gemini", model="gemini-3.1-flash-lite", encrypted_api_key="key")

    result = await agent.run(config, "Tell me about Apple.")
    assert "Apple Inc (AAPL)" in result
    assert len(provider.received_messages) == 3


async def test_agent_max_rounds_loop_protection() -> None:
    # Always returns a tool call without producing final text
    infinite_steps = [
        LLMStepResponse(
            content=None,
            tool_calls=[ToolCall(id=f"call_{i}", name="get_stock_price", arguments={"ticker": "NVDA"})],
        )
        for i in range(10)
    ]
    provider = ScriptedLLMProvider(infinite_steps)
    service = FakeConfiguredService(provider)
    tool_registry = ToolRegistry([GetStockPriceTool(provider=FakeFinnhubProvider())])
    agent = AIAgent(llm_service=service, tool_registry=tool_registry, max_rounds=5)
    config = UserLLMConfiguration(provider="gemini", model="gemini-3.1-flash-lite", encrypted_api_key="key")

    result = await agent.run(config, "Loop test")
    assert "maximum number of tool execution rounds" in result
    assert len(provider.received_messages) == 5


# --- Provider Tool Definition and Parsing tests ------------------------------


def test_gemini_provider_tool_payload_and_parsing() -> None:
    tools = [
        ToolDefinition(
            name="get_stock_price",
            description="Get stock price",
            input_schema={"type": "object", "properties": {"ticker": {"type": "string"}}},
        )
    ]

    payload = GeminiProvider._build_payload(
        [{"role": "user", "content": "How is NVDA?"}],
        model="gemini-3.1-flash-lite",
        tools=tools,
    )

    assert "tools" in payload
    assert payload["tools"][0]["type"] == "function"
    assert payload["tools"][0]["name"] == "get_stock_price"
    assert payload["tools"][0]["description"] == "Get stock price"
    assert payload["tools"][0]["parameters"]["type"] == "object"

    # Test payload construction with assistant function_call and tool function_result history
    history_messages = [
        {"role": "user", "content": "How is NVDA?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [ToolCall(id="call_999", name="get_stock_price", arguments={"ticker": "NVDA"})],
        },
        {
            "role": "tool",
            "call_id": "call_999",
            "name": "get_stock_price",
            "content": {"price": 125.5, "ticker": "NVDA"},
        },
    ]

    history_payload = GeminiProvider._build_payload(
        history_messages,
        model="gemini-3.1-flash-lite",
        tools=tools,
    )

    # Assert no 'args' parameter exists anywhere in input steps
    payload_str = json.dumps(history_payload)
    assert '"args":' not in payload_str, "Gemini input payload must not contain 'args' key"

    input_steps = history_payload["input"]

    # Assert exact turn sequence ordering: user_input -> function_call -> function_result
    assert len(input_steps) == 3
    assert input_steps[0]["type"] == "user_input"
    assert input_steps[1]["type"] == "function_call"
    assert input_steps[2]["type"] == "function_result"

    fc_step = input_steps[1]
    assert fc_step["name"] == "get_stock_price"
    assert fc_step["arguments"] == {"ticker": "NVDA"}
    assert fc_step["id"] == "call_999"

    fr_step = input_steps[2]
    assert fr_step["name"] == "get_stock_price"
    assert fr_step["call_id"] == "call_999"
    assert isinstance(fr_step["result"], list)
    assert fr_step["result"][0]["type"] == "text"
    parsed_res = json.loads(fr_step["result"][0]["text"])
    assert parsed_res["price"] == 125.5

    # Test sequential multi-tool calling turn sequence ordering:
    # user_input -> function_call (1) -> function_result (1) -> function_call (2) -> function_result (2) -> model_output
    multi_history_messages = [
        {"role": "user", "content": "Analyze Apple"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [ToolCall(id="call_1", name="search_company", arguments={"query": "Apple"})],
        },
        {"role": "tool", "call_id": "call_1", "name": "search_company", "content": {"ticker": "AAPL"}},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [ToolCall(id="call_2", name="get_stock_price", arguments={"ticker": "AAPL"})],
        },
        {"role": "tool", "call_id": "call_2", "name": "get_stock_price", "content": {"price": 180.0}},
        {"role": "assistant", "content": "Apple is doing well."},
    ]

    multi_payload = GeminiProvider._build_payload(
        multi_history_messages,
        model="gemini-3.1-flash-lite",
        tools=tools,
    )
    multi_steps = multi_payload["input"]
    step_types = [s["type"] for s in multi_steps]
    assert step_types == [
        "user_input",
        "function_call",
        "function_result",
        "function_call",
        "function_result",
        "model_output",
    ]

    # Verify no function_call step is separated from user_input or function_result by model_output or invalid items
    for idx, s in enumerate(multi_steps):
        if s["type"] == "function_call":
            prev_type = multi_steps[idx - 1]["type"]
            assert prev_type in {"user_input", "function_result"}, (
                f"function_call at index {idx} must immediately follow user_input or function_result, "
                f"but followed {prev_type}"
            )

    # Test tool call extraction from flat Interactions API response step (accepting arguments or args)
    data_flat = {
        "steps": [
            {
                "type": "function_call",
                "id": "call_123",
                "name": "get_stock_price",
                "arguments": {"ticker": "NVDA"},
            }
        ]
    }
    extracted_flat = GeminiProvider._extract_tool_calls(data_flat)
    assert len(extracted_flat) == 1
    assert extracted_flat[0].id == "call_123"
    assert extracted_flat[0].name == "get_stock_price"
    assert extracted_flat[0].arguments == {"ticker": "NVDA"}

    # Test tool call extraction from legacy nested model_output step
    data_nested = {
        "steps": [
            {
                "type": "model_output",
                "content": [
                    {
                        "type": "function_call",
                        "name": "get_stock_price",
                        "args": {"ticker": "NVDA"},
                    }
                ],
            }
        ]
    }
    extracted_nested = GeminiProvider._extract_tool_calls(data_nested)
    assert len(extracted_nested) == 1
    assert extracted_nested[0].name == "get_stock_price"
    assert extracted_nested[0].arguments == {"ticker": "NVDA"}


async def test_gemini_http_integration_exact_payload() -> None:
    recorded_requests: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        recorded_requests.append(payload)

        # Turn 1 response: return function_call + interaction id
        if len(recorded_requests) == 1:
            return httpx.Response(
                200,
                json={
                    "id": "interactions/abc12345",
                    "status": "completed",
                    "steps": [
                        {
                            "type": "function_call",
                            "id": "call_abc123",
                            "name": "get_stock_price",
                            "arguments": {"ticker": "NVDA"},
                        }
                    ],
                },
            )

        # Turn 2 response: return final text
        return httpx.Response(
            200,
            json={
                "id": "interactions/abc123456",
                "status": "completed",
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": "NVIDIA is trading at $125.50."}],
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = GeminiProvider("test-key", "gemini-3.1-flash-lite", client=client)
        service = FakeConfiguredService(provider)
        tool_registry = ToolRegistry([GetStockPriceTool(provider=FakeFinnhubProvider())])
        agent = AIAgent(llm_service=service, tool_registry=tool_registry)
        config = UserLLMConfiguration(provider="gemini", model="gemini-3.1-flash-lite", encrypted_api_key="key")

        result = await agent.run(config, "How is NVIDIA doing?")
        assert result == "NVIDIA is trading at $125.50."

    assert len(recorded_requests) == 2

    # Turn 1 payload assertions
    req1 = recorded_requests[0]
    assert req1["model"] == "gemini-3.1-flash-lite"
    assert req1["store"] is True
    assert req1["input"] == "How is NVIDIA doing?"
    assert req1["tools"][0] == {
        "type": "function",
        "name": "get_stock_price",
        "description": "Get current stock quote, market price data, and technical analysis context for a ticker symbol (e.g., NVDA, AAPL).",
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "The stock ticker symbol (e.g. NVDA, AAPL)",
                }
            },
            "required": ["ticker"],
        },
    }

    # Turn 2 payload assertions
    req2 = recorded_requests[1]
    assert req2["model"] == "gemini-3.1-flash-lite"
    assert req2["previous_interaction_id"] == "interactions/abc12345"
    steps2 = req2["input"]
    assert len(steps2) == 1
    assert steps2[0]["type"] == "function_result"
    assert steps2[0]["name"] == "get_stock_price"
    assert steps2[0]["call_id"] == "call_abc123"
    result_data = json.loads(steps2[0]["result"][0]["text"])
    assert result_data["ticker"] == "NVDA"
    assert result_data["price"] == 125.5


def test_openai_provider_tool_payload_and_parsing() -> None:
    provider = OpenAIProvider(api_key="key", model="gpt-4.1-mini")
    tools = [
        ToolDefinition(
            name="get_stock_price",
            description="Get stock price",
            input_schema={"type": "object", "properties": {"ticker": {"type": "string"}}},
        )
    ]

    messages = [
        {"role": "user", "content": "How is NVDA?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [ToolCall(id="call_1", name="get_stock_price", arguments={"ticker": "NVDA"})],
        },
        {"role": "tool", "call_id": "call_1", "name": "get_stock_price", "content": {"price": 100}},
    ]

    formatted = provider._build_messages(messages)
    assert formatted[1]["role"] == "assistant"
    assert formatted[1]["tool_calls"][0]["function"]["name"] == "get_stock_price"
    assert formatted[2]["role"] == "tool"
    assert formatted[2]["tool_call_id"] == "call_1"


# --- Telegram Integration tests ---------------------------------------------


async def test_telegram_natural_queries_reach_agent() -> None:
    provider = ScriptedLLMProvider([
        LLMStepResponse(
            content=None,
            tool_calls=[ToolCall(id="call_1", name="get_stock_price", arguments={"ticker": "NVDA"})],
        ),
        LLMStepResponse(content="NVIDIA is trading at $125.50 today.", tool_calls=[]),
    ])
    service = FakeConfiguredService(provider)
    tool_registry = ToolRegistry([GetStockPriceTool(provider=FakeFinnhubProvider())])

    telegram_service = TelegramAnalysisService(
        stock_service=None,
        llm_service=service,
        analysis_service=None,
        tool_registry=tool_registry,
    )

    user = SimpleNamespace(
        llm_configuration=UserLLMConfiguration(
            provider="gemini",
            model="gemini-3.1-flash-lite",
            encrypted_api_key="key",
        )
    )

    queries = [
        "How is NVIDIA doing?",
        "What's Apple's price?",
        "Tell me about Microsoft.",
        "Apple",
        "AAPL",
    ]

    for query in queries:
        provider.current_step = 0
        response = await telegram_service.analyze(user, query)
        assert "NVIDIA is trading at $125.50 today." in response


async def main() -> None:
    await test_get_stock_price_tool()
    await test_get_company_tool()
    await test_search_company_tool()
    test_tool_registry()
    await test_registry_execution_and_validation()
    await test_agent_returns_final_text_directly()
    await test_agent_executes_single_tool_and_returns_final_text()
    await test_agent_executes_multi_step_sequential_tools()
    await test_agent_max_rounds_loop_protection()
    test_gemini_provider_tool_payload_and_parsing()
    await test_gemini_http_integration_exact_payload()
    test_openai_provider_tool_payload_and_parsing()
    await test_telegram_natural_queries_reach_agent()
    print("AI Agent & Tool Calling test suite passed successfully!")


if __name__ == "__main__":
    asyncio.run(main())

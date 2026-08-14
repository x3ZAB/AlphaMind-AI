import asyncio
import json
from datetime import date, timedelta
from types import SimpleNamespace

import httpx

from app.providers.finnhub import FinnhubProvider
from app.services.analysis_context import (
    AnalysisContext,
    build_analysis_context,
    compute_distance_from_sma,
    compute_period_return,
    compute_sma,
    compute_volatility,
)
from app.services.llm_analysis import LLMAnalysisService
from app.services.stock_analysis import StockAnalysisService
from app.services.telegram_analysis import TelegramAnalysisService

COMPANY = {
    "name": "NVIDIA Corporation",
    "ticker": "NVDA",
    "finnhubIndustry": "Technology",
    "marketCapitalization": 2100000,
    "shareOutstanding": 2460000000,
}

QUOTE = {
    "c": 155.0,
    "d": 2.0,
    "dp": 1.31,
    "h": 156.5,
    "l": 153.0,
    "o": 154.0,
    "pc": 153.0,
}


def make_candles(
    count: int,
    start: float = 100.0,
    step: float = 1.0,
):
    candles = []
    price = start
    start_date = date(2026, 1, 1)

    for index in range(count):
        candles.append(
            {
                "date": (
                    start_date + timedelta(days=index)
                ).isoformat(),
                "close": price,
            }
        )
        price += step

    return candles


# --- metric helpers ---------------------------------------------------------


def test_sma_calculation() -> None:
    assert compute_sma([1, 2, 3, 4, 5], 3) == 4.0
    assert compute_sma([5, 10], 2) == 7.5


def test_sma_insufficient_returns_none() -> None:
    assert compute_sma([1, 2, 3], 5) is None
    assert compute_sma([], 20) is None
    assert compute_sma([1, 2, 3], 0) is None


def test_volatility_calculation() -> None:
    # returns = [1.0, 0.5]; sample std ~= 0.353553
    assert compute_volatility([1, 2, 3]) == 0.353553


def test_volatility_insufficient_returns_none() -> None:
    assert compute_volatility([]) is None
    assert compute_volatility([100]) is None
    # one return is not enough for a sample standard deviation
    assert compute_volatility([100, 101]) is None


def test_period_return_calculation() -> None:
    assert compute_period_return([1, 2, 3]) == 2.0


def test_period_return_insufficient_returns_none() -> None:
    assert compute_period_return([]) is None
    assert compute_period_return([100]) is None
    assert compute_period_return([0, 100]) is None


def test_distance_from_sma_calculation() -> None:
    assert compute_distance_from_sma(4.0, 4.0) == 0.0
    assert compute_distance_from_sma(5.0, 4.0) == 0.25


def test_distance_from_sma_unavailable_returns_none() -> None:
    assert compute_distance_from_sma(None, 4.0) is None
    assert compute_distance_from_sma(5.0, None) is None
    assert compute_distance_from_sma(5.0, 0.0) is None


# --- context creation -------------------------------------------------------


def test_full_analysis_context_creation() -> None:
    candles = make_candles(60)
    context = build_analysis_context(COMPANY, QUOTE, candles)

    assert isinstance(context, AnalysisContext)
    assert context.company.name == "NVIDIA Corporation"
    assert context.company.ticker == "NVDA"
    assert context.company.industry == "Technology"
    assert context.company.market_cap == 2100000
    assert context.company.shares_outstanding == 2460000000

    assert context.market.price == 155.0
    assert context.market.change == 2.0
    assert context.market.change_percent == 1.31
    assert context.market.high == 156.5
    assert context.market.low == 153.0
    assert context.market.open == 154.0
    assert context.market.previous_close == 153.0

    assert context.historical.count == 60
    assert context.historical.from_date == "2026-01-01"
    assert context.historical.to_date == "2026-03-01"
    assert len(context.historical.recent) == 60

    # 60 closes are enough for both SMA20 and SMA50.
    assert context.metrics.sma20 is not None
    assert context.metrics.sma50 is not None
    assert context.metrics.volatility is not None
    assert context.metrics.period_return is not None
    assert context.metrics.distance_from_sma20 is not None
    assert context.metrics.distance_from_sma50 is not None


def test_context_to_dict_is_serializable() -> None:
    context = build_analysis_context(COMPANY, QUOTE, make_candles(60))
    raw = json.dumps(context.to_dict(), default=str)
    assert '"sma20"' in raw
    assert '"ticker"' in raw


def test_insufficient_historical_data_yields_nulls() -> None:
    # A single close cannot support SMA20/SMA50/volatility/period return.
    context = build_analysis_context(COMPANY, QUOTE, make_candles(1))

    assert context.metrics.sma20 is None
    assert context.metrics.sma50 is None
    assert context.metrics.volatility is None
    assert context.metrics.period_return is None
    assert context.metrics.distance_from_sma20 is None
    assert context.metrics.distance_from_sma50 is None


def test_partial_historical_data_returns_partial_metrics() -> None:
    # 30 closes support SMA20 but not SMA50.
    context = build_analysis_context(COMPANY, QUOTE, make_candles(30))

    assert context.metrics.sma20 is not None
    assert context.metrics.sma50 is None
    assert context.metrics.period_return is not None
    assert context.metrics.volatility is not None


def test_missing_company_data() -> None:
    context = build_analysis_context(None, QUOTE, make_candles(60))

    assert context.company.name is None
    assert context.company.ticker is None
    assert context.company.industry is None
    assert context.company.market_cap is None
    assert context.company.shares_outstanding is None
    # Market and metrics are still computed.
    assert context.market.price == 155.0
    assert context.metrics.sma20 is not None


def test_missing_quote_data() -> None:
    context = build_analysis_context(COMPANY, None, make_candles(60))

    assert context.market.price is None
    assert context.market.change is None
    assert context.market.previous_close is None
    # Without a quote we fall back to the last close as the reference price.
    assert context.metrics.distance_from_sma20 is not None
    assert context.company.name == "NVIDIA Corporation"


def test_missing_everything_returns_empty_but_valid_context() -> None:
    context = build_analysis_context(None, None, None)

    assert context.company.name is None
    assert context.market.price is None
    assert context.historical.count == 0
    assert context.historical.recent == []
    assert context.metrics.sma20 is None
    assert context.metrics.sma50 is None


# --- LLM receives the enriched context --------------------------------------


def test_llm_receives_structured_analysis_context() -> None:
    context = build_analysis_context(COMPANY, QUOTE, make_candles(60))

    messages = LLMAnalysisService().build_messages(
        question="analyze NVDA",
        analysis_context=context.to_dict(),
    )

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "analyze NVDA" in messages[1]["content"]
    # Structured values are present, null guidance is explicit.
    assert "NVIDIA Corporation" in messages[1]["content"]
    assert "sma20" in messages[1]["content"]
    assert "do not invent a number" in messages[1]["content"]


def test_llm_fallback_without_context_still_works() -> None:
    messages = LLMAnalysisService().build_messages(
        question="analyze NVDA",
        company={"ticker": "NVDA"},
        current_price={"c": 100},
    )
    assert "NVDA" in messages[1]["content"]
    assert "analysis_context" not in messages[1]["content"]


# --- wiring: StockAnalysisService -> context --------------------------------


class FakeProvider:
    async def get_company(self, ticker: str) -> dict:
        return dict(COMPANY)

    async def get_stock_price(self, ticker: str) -> dict:
        return dict(QUOTE)

    async def get_stock_candles(self, ticker, *, lookback_days=250):
        return make_candles(60)


async def test_stock_analysis_service_builds_context() -> None:
    service = StockAnalysisService(provider=FakeProvider())
    result = await service.analyze("NVDA")

    assert result["company"]["ticker"] == "NVDA"
    assert result["quote"]["c"] == 155.0
    assert result["context"]["metrics"]["sma20"] is not None
    assert result["context"]["historical"]["count"] == 60


class FailureInjectionProvider:
    """A provider that can be told to fail the historical or quote fetch."""

    def __init__(
        self,
        *,
        candle_error: Exception | None = None,
        quote_error: Exception | None = None,
    ):
        self.candle_error = candle_error
        self.quote_error = quote_error

    async def get_company(self, ticker: str) -> dict:
        return dict(COMPANY)

    async def get_stock_price(self, ticker: str) -> dict:
        if self.quote_error is not None:
            raise self.quote_error
        return dict(QUOTE)

    async def get_stock_candles(self, ticker, *, lookback_days=250):
        if self.candle_error is not None:
            raise self.candle_error
        return make_candles(60)

    async def search_company(self, query: str) -> dict:
        return {"result": [{"symbol": query.upper()}]}


def _http_error(status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request(
        "GET",
        "https://finnhub.io/api/v1/stock/candle",
    )
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(
        f"Client error '{status_code}'",
        request=request,
        response=response,
    )


def _connect_error() -> httpx.ConnectError:
    request = httpx.Request(
        "GET",
        "https://finnhub.io/api/v1/stock/candle",
    )
    return httpx.ConnectError("connection refused", request=request)


async def test_historical_success_calculates_metrics() -> None:
    service = StockAnalysisService(provider=FailureInjectionProvider())
    result = await service.analyze("NVDA")

    assert result["context"]["historical"]["available"] is True
    assert result["context"]["historical"]["reason"] is None
    assert result["context"]["historical"]["count"] == 60
    metrics = result["context"]["metrics"]
    assert metrics["sma20"] is not None
    assert metrics["sma50"] is not None
    assert metrics["volatility"] is not None
    assert metrics["period_return"] is not None


async def test_historical_403_falls_back_gracefully() -> None:
    service = StockAnalysisService(
        provider=FailureInjectionProvider(candle_error=_http_error(403))
    )
    result = await service.analyze("NVDA")

    # Current market data is preserved; only history is degraded.
    assert result["quote"]["c"] == 155.0

    history = result["context"]["historical"]
    assert history["available"] is False
    assert history["reason"] == "unavailable"
    assert history["count"] == 0
    assert history["recent"] == []

    metrics = result["context"]["metrics"]
    assert metrics["sma20"] is None
    assert metrics["sma50"] is None
    assert metrics["volatility"] is None
    assert metrics["period_return"] is None
    assert metrics["distance_from_sma20"] is None
    assert metrics["distance_from_sma50"] is None


async def test_historical_429_falls_back_gracefully() -> None:
    service = StockAnalysisService(
        provider=FailureInjectionProvider(candle_error=_http_error(429))
    )
    result = await service.analyze("NVDA")

    assert result["quote"]["c"] == 155.0
    assert result["context"]["historical"]["available"] is False
    assert result["context"]["historical"]["reason"] == "unavailable"
    assert result["context"]["metrics"]["sma20"] is None
    assert result["context"]["metrics"]["period_return"] is None


async def test_historical_network_failure_falls_back_gracefully() -> None:
    service = StockAnalysisService(
        provider=FailureInjectionProvider(candle_error=_connect_error())
    )
    result = await service.analyze("NVDA")

    assert result["quote"]["c"] == 155.0
    assert result["context"]["historical"]["available"] is False
    assert result["context"]["historical"]["reason"] == "unavailable"
    assert result["context"]["metrics"]["volatility"] is None


async def test_quote_failure_still_fails_analysis() -> None:
    service = StockAnalysisService(
        provider=FailureInjectionProvider(quote_error=_connect_error())
    )

    try:
        await service.analyze("NVDA")
    except httpx.ConnectError:
        return
    # Quote (current market data) is required — analysis must not succeed.
    raise AssertionError(
        "stock analysis should fail when current quote is unavailable"
    )


class FakeLLMService:
    async def generate(self, configuration, messages, **kwargs) -> str:
        self.received_messages = messages
        return "analysis done"


class ContextStockService:
    async def analyze_query(self, query: str) -> dict:
        context = build_analysis_context(COMPANY, QUOTE, make_candles(60))
        return {
            "company": dict(COMPANY),
            "quote": dict(QUOTE),
            "context": context.to_dict(),
        }


async def test_telegram_analysis_passes_context_to_llm() -> None:
    llm = FakeLLMService()
    service = TelegramAnalysisService(
        stock_service=ContextStockService(),
        llm_service=llm,
        analysis_service=LLMAnalysisService(),
    )

    user = SimpleNamespace(llm_configuration=object())
    response = await service.analyze(user, "analyze NVDA")

    assert response == "analysis done"
    content = llm.received_messages[1]["content"]
    assert "sma20" in content
    assert "NVIDIA Corporation" in content


# --- historical candle parsing (Finnhub) ------------------------------------


async def test_finnhub_candles_are_parsed_oldest_first() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/stock/candle")
        assert request.url.params["symbol"] == "NVDA"
        assert request.url.params["resolution"] == "D"
        return httpx.Response(
            200,
            json={
                "s": "ok",
                "t": [1767225600, 1767312000],
                "c": [100.5, 101.25],
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = FinnhubProvider(client=client)
        candles = await provider.get_stock_candles(
            "nvda",
            lookback_days=250,
        )

    assert len(candles) == 2
    assert candles[0]["date"] == "2026-01-01"
    assert candles[0]["close"] == 100.5
    assert candles[1]["close"] == 101.25


async def test_finnhub_no_data_returns_empty_list() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"s": "no_data"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = FinnhubProvider(client=client)
        candles = await provider.get_stock_candles("NVDA")

    assert candles == []


async def main() -> None:
    test_sma_calculation()
    test_sma_insufficient_returns_none()
    test_volatility_calculation()
    test_volatility_insufficient_returns_none()
    test_period_return_calculation()
    test_period_return_insufficient_returns_none()
    test_distance_from_sma_calculation()
    test_distance_from_sma_unavailable_returns_none()
    test_full_analysis_context_creation()
    test_context_to_dict_is_serializable()
    test_insufficient_historical_data_yields_nulls()
    test_partial_historical_data_returns_partial_metrics()
    test_missing_company_data()
    test_missing_quote_data()
    test_missing_everything_returns_empty_but_valid_context()
    test_llm_receives_structured_analysis_context()
    test_llm_fallback_without_context_still_works()
    await test_stock_analysis_service_builds_context()
    await test_historical_success_calculates_metrics()
    await test_historical_403_falls_back_gracefully()
    await test_historical_429_falls_back_gracefully()
    await test_historical_network_failure_falls_back_gracefully()
    await test_quote_failure_still_fails_analysis()
    await test_telegram_analysis_passes_context_to_llm()
    await test_finnhub_candles_are_parsed_oldest_first()
    await test_finnhub_no_data_returns_empty_list()
    print("Analysis context tests passed")


if __name__ == "__main__":
    asyncio.run(main())

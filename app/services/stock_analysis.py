from app.providers.base import BaseProvider
from app.providers.finnhub import FinnhubProvider
from app.services.analysis_context import (
    DEFAULT_LOOKBACK_DAYS,
    build_analysis_context,
)


class StockAnalysisService:

    def __init__(self, provider: BaseProvider | None = None):
        self.provider = provider or FinnhubProvider()

    async def analyze(self, ticker: str) -> dict:
        company = await self.provider.get_company(ticker)
        quote = await self.provider.get_stock_price(ticker)
        candles = await self.provider.get_stock_candles(
            ticker,
            lookback_days=DEFAULT_LOOKBACK_DAYS,
        )

        context = build_analysis_context(
            company,
            quote,
            candles,
            lookback_days=DEFAULT_LOOKBACK_DAYS,
        )

        return {
            "company": company,
            "quote": quote,
            "context": context.to_dict(),
        }

    async def analyze_query(self, query: str) -> dict | None:
        search_result = await self.provider.search_company(query)

        results = search_result.get("result", [])

        if not results:
            return None

        query_upper = query.strip().upper()

        selected = next(
            (
                item
                for item in results
                if item.get("symbol", "").upper() == query_upper
            ),
            results[0],
        )

        ticker = selected.get("symbol")

        if not ticker:
            return None

        return await self.analyze(ticker)

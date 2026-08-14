import logging

import httpx

from app.providers.base import BaseProvider
from app.providers.finnhub import FinnhubProvider
from app.services.analysis_context import (
    DEFAULT_LOOKBACK_DAYS,
    build_analysis_context,
)

logger = logging.getLogger(__name__)


class StockAnalysisService:

    def __init__(self, provider: BaseProvider | None = None):
        self.provider = provider or FinnhubProvider()

    async def analyze(self, ticker: str) -> dict:
        company = await self.provider.get_company(ticker)
        quote = await self.provider.get_stock_price(ticker)

        # Historical candles are OPTIONAL. A failure must not sink the whole
        # analysis: fall back to an empty dataset so the context reports the
        # history as unavailable and skips the derived metrics. Only a failure
        # of the current market data (quote/company) should fail the lookup.
        candles: list = []
        historical_available = True
        historical_reason = None

        try:
            candles = await self.provider.get_stock_candles(
                ticker,
                lookback_days=DEFAULT_LOOKBACK_DAYS,
            )
        except httpx.HTTPError as exc:
            historical_available = False
            historical_reason = "unavailable"
            # Log only the exception class and symbol — never the request URL,
            # which embeds the Finnhub API token, and never the raw payload.
            logger.warning(
                "Historical candles unavailable for %s: %s",
                ticker,
                type(exc).__name__,
            )

        context = build_analysis_context(
            company,
            quote,
            candles,
            lookback_days=DEFAULT_LOOKBACK_DAYS,
            historical_available=historical_available,
            historical_reason=historical_reason,
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

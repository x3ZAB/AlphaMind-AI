from typing import Any

from app.providers.base import BaseProvider
from app.providers.finnhub import FinnhubProvider
from app.tools.base import Tool


class GetStockPriceTool(Tool):
    def __init__(
        self,
        provider: BaseProvider | None = None,
        stock_service: Any | None = None,
    ) -> None:
        self.provider = provider or FinnhubProvider()
        self.stock_service = stock_service
        super().__init__(
            name="get_stock_price",
            description="Get current stock quote, market price data, and technical analysis context for a ticker symbol (e.g., NVDA, AAPL).",
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "The stock ticker symbol (e.g. NVDA, AAPL)",
                    }
                },
                "required": ["ticker"],
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ticker = arguments.get("ticker")
        if not ticker or not isinstance(ticker, str):
            return {"error": "A valid string ticker is required"}

        ticker_upper = ticker.strip().upper()
        try:
            if self.stock_service is not None:
                if hasattr(self.stock_service, "analyze"):
                    stock_data = await self.stock_service.analyze(ticker_upper)
                elif hasattr(self.stock_service, "analyze_query"):
                    stock_data = await self.stock_service.analyze_query(ticker_upper)
                else:
                    stock_data = None

                if stock_data:
                    quote = stock_data.get("quote") or {}
                    company = stock_data.get("company") or {}
                    context = stock_data.get("context") or {}
                    return {
                        "ticker": ticker_upper,
                        "name": company.get("name"),
                        "price": quote.get("c"),
                        "change": quote.get("d"),
                        "change_percent": quote.get("dp"),
                        "high": quote.get("h"),
                        "low": quote.get("l"),
                        "open": quote.get("o"),
                        "previous_close": quote.get("pc"),
                        "company": company,
                        "quote": quote,
                        "context": context,
                    }

            from app.services.stock_analysis import StockAnalysisService
            analysis_service = StockAnalysisService(self.provider)
            stock_data = await analysis_service.analyze(ticker_upper)

            quote = stock_data.get("quote") or {}
            company = stock_data.get("company") or {}
            context = stock_data.get("context") or {}

            if not quote or quote.get("c") is None:
                return {
                    "ticker": ticker_upper,
                    "error": f"No price data available for {ticker_upper}",
                }

            return {
                "ticker": ticker_upper,
                "name": company.get("name"),
                "price": quote.get("c"),
                "change": quote.get("d"),
                "change_percent": quote.get("dp"),
                "high": quote.get("h"),
                "low": quote.get("l"),
                "open": quote.get("o"),
                "previous_close": quote.get("pc"),
                "company": company,
                "quote": quote,
                "context": context,
            }
        except Exception as exc:
            return {
                "ticker": ticker_upper,
                "error": f"Failed to retrieve stock price: {str(exc)}",
            }


class GetCompanyTool(Tool):
    def __init__(self, provider: BaseProvider | None = None) -> None:
        self.provider = provider or FinnhubProvider()
        super().__init__(
            name="get_company",
            description="Get company profile, industry, market capitalization, and share details for a ticker symbol.",
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "The stock ticker symbol (e.g. NVDA, AAPL)",
                    }
                },
                "required": ["ticker"],
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ticker = arguments.get("ticker")
        if not ticker or not isinstance(ticker, str):
            return {"error": "A valid string ticker is required"}

        ticker_upper = ticker.strip().upper()
        try:
            profile = await self.provider.get_company(ticker_upper)
            if not profile or not profile.get("name"):
                return {
                    "ticker": ticker_upper,
                    "error": f"Company profile not found for {ticker_upper}",
                }

            return {
                "ticker": ticker_upper,
                "name": profile.get("name"),
                "industry": profile.get("finnhubIndustry"),
                "market_cap": profile.get("marketCapitalization"),
                "shares_outstanding": profile.get("shareOutstanding"),
            }
        except Exception as exc:
            return {
                "ticker": ticker_upper,
                "error": f"Failed to retrieve company profile: {str(exc)}",
            }


class SearchCompanyTool(Tool):
    def __init__(self, provider: BaseProvider | None = None) -> None:
        self.provider = provider or FinnhubProvider()
        super().__init__(
            name="search_company",
            description="Search for a company by name to resolve its stock ticker symbol (e.g., 'Apple', 'NVIDIA', 'Tesla').",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Company name or keyword to search for (e.g. Apple, Microsoft)",
                    }
                },
                "required": ["query"],
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = arguments.get("query")
        if not query or not isinstance(query, str):
            return {"error": "A valid string search query is required"}

        query_str = query.strip()
        try:
            search_data = await self.provider.search_company(query_str)
            results = search_data.get("result", []) if search_data else []

            if not results:
                return {
                    "query": query_str,
                    "error": f"No companies found matching '{query_str}'",
                }

            query_upper = query_str.upper()
            best_match = next(
                (
                    item
                    for item in results
                    if item.get("symbol", "").upper() == query_upper
                ),
                results[0],
            )

            ticker = best_match.get("symbol")
            name = best_match.get("description", best_match.get("displaySymbol", ticker))

            return {
                "query": query_str,
                "ticker": ticker,
                "name": name,
            }
        except Exception as exc:
            return {
                "query": query_str,
                "error": f"Failed to search for company: {str(exc)}",
            }

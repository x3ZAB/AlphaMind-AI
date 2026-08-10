from app.providers.finnhub import FinnhubProvider


class StockAnalysisService:

    def __init__(self):
        self.provider = FinnhubProvider()

    async def analyze(self, ticker: str) -> dict:
        company = await self.provider.get_company(ticker)
        quote = await self.provider.get_stock_price(ticker)

        return {
            "company": company,
            "quote": quote,
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
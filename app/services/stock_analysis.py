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
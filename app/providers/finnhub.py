import httpx

from app.core.config import settings
from app.providers.base import BaseProvider


class FinnhubProvider(BaseProvider):

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self):
        self.api_key = settings.FINNHUB_API_KEY

    async def get_company(self, ticker: str) -> dict:
        url = f"{self.BASE_URL}/stock/profile2"

        params = {
            "symbol": ticker.upper(),
            "token": self.api_key,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)

        response.raise_for_status()

        return response.json()

    async def get_stock_price(self, ticker: str) -> dict:
        url = f"{self.BASE_URL}/quote"

        params = {
            "symbol": ticker.upper(),
            "token": self.api_key,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)

        response.raise_for_status()

        return response.json()
from datetime import datetime, timezone

import httpx

from app.core.config import settings
from app.providers.base import BaseProvider


class FinnhubProvider(BaseProvider):

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self, client: httpx.AsyncClient | None = None):
        self.api_key = settings.FINNHUB_API_KEY
        self._client = client

    async def get_company(self, ticker: str) -> dict:
        url = f"{self.BASE_URL}/stock/profile2"

        params = {
            "symbol": ticker.upper(),
            "token": self.api_key,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params=params,
            )

        response.raise_for_status()

        return response.json()

    async def get_stock_price(self, ticker: str) -> dict:
        url = f"{self.BASE_URL}/quote"

        params = {
            "symbol": ticker.upper(),
            "token": self.api_key,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params=params,
            )

        response.raise_for_status()

        return response.json()

    async def get_stock_candles(
        self,
        ticker: str,
        *,
        resolution: str = "D",
        lookback_days: int = 250,
    ) -> list[dict]:
        """Return daily candles as ``{"date", "close"}`` dicts, oldest first.

        Uses the already-integrated Finnhub stock-candle endpoint. Returns an
        empty list (rather than failing the whole analysis) when the market
        has no data for the symbol in the requested window.
        """
        now = datetime.now(timezone.utc)
        to_timestamp = int(now.timestamp())
        from_timestamp = to_timestamp - lookback_days * 86400

        url = f"{self.BASE_URL}/stock/candle"

        params = {
            "symbol": ticker.upper(),
            "resolution": resolution,
            "from": from_timestamp,
            "to": to_timestamp,
            "token": self.api_key,
        }

        request_params = params

        if self._client is not None:
            response = await self._client.get(
                url,
                params=request_params,
            )
        else:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    params=request_params,
                )

        response.raise_for_status()

        payload = response.json()

        if payload.get("s") != "ok":
            return []

        closes = payload.get("c") or []
        timestamps = payload.get("t") or []

        candles: list[dict] = []

        for timestamp, close in zip(timestamps, closes):
            if timestamp is None or close is None:
                continue

            date = datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc,
            ).date().isoformat()

            candles.append(
                {
                    "date": date,
                    "close": float(close),
                }
            )

        return candles

    async def search_company(self, query: str) -> dict:
        url = f"{self.BASE_URL}/search"

        params = {
            "q": query,
            "token": self.api_key,
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params=params,
            )

        response.raise_for_status()

        return response.json()
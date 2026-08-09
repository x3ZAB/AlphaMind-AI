from datetime import datetime
from decimal import Decimal

from app.models import StockPrice
from app.repositories import StockPriceRepository


class StockPriceService:
    def __init__(self, repository: StockPriceRepository):
        self.repository = repository

    def add_price(
        self,
        company_id: int,
        price: Decimal,
        timestamp: datetime,
    ) -> StockPrice:
        if price < 0:
            raise ValueError("Stock price cannot be negative")

        return self.repository.create(
            company_id=company_id,
            price=price,
            timestamp=timestamp,
        )

    def get_latest_price(
        self,
        company_id: int,
    ) -> StockPrice | None:
        return self.repository.get_latest(company_id)

    def get_price_history(
        self,
        company_id: int,
        limit: int = 100,
    ) -> list[StockPrice]:
        if limit <= 0:
            raise ValueError("Limit must be greater than zero")

        return self.repository.get_history(
            company_id=company_id,
            limit=limit,
        )
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import StockPrice


class StockPriceRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        company_id: int,
        price: Decimal,
        timestamp: datetime,
    ) -> StockPrice:
        stock_price = StockPrice(
            company_id=company_id,
            price=price,
            timestamp=timestamp,
        )

        self.db.add(stock_price)
        self.db.commit()
        self.db.refresh(stock_price)

        return stock_price

    def get_by_id(self, stock_price_id: int) -> StockPrice | None:
        statement = select(StockPrice).where(
            StockPrice.id == stock_price_id
        )
        return self.db.scalar(statement)

    def get_latest(self, company_id: int) -> StockPrice | None:
        statement = (
            select(StockPrice)
            .where(StockPrice.company_id == company_id)
            .order_by(StockPrice.timestamp.desc())
            .limit(1)
        )

        return self.db.scalar(statement)

    def get_history(
        self,
        company_id: int,
        limit: int = 100,
    ) -> list[StockPrice]:
        statement = (
            select(StockPrice)
            .where(StockPrice.company_id == company_id)
            .order_by(StockPrice.timestamp.desc())
            .limit(limit)
        )

        return list(self.db.scalars(statement).all())
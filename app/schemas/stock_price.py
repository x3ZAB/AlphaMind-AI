from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class StockPriceCreate(BaseModel):
    company_id: int
    price: Decimal
    timestamp: datetime


class StockPriceResponse(BaseModel):
    id: int
    company_id: int
    price: Decimal
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)
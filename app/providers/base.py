from abc import ABC, abstractmethod
from typing import Any


class BaseProvider(ABC):

    @abstractmethod
    async def get_company(self, ticker: str) -> dict[str, Any]:
        pass

    @abstractmethod
    async def get_stock_price(self, ticker: str) -> dict[str, Any]:
        pass
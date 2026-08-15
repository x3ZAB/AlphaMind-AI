from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class Tool(ABC):
    name: str
    description: str
    input_schema: dict[str, Any]

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute the tool with the given arguments and return a structured dictionary."""
        ...

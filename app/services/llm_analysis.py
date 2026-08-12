import json
from typing import Any

from app.llm.prompts import ALPHAMIND_SYSTEM_PROMPT


class LLMAnalysisService:
    def build_messages(
        self,
        *,
        question: str,
        company: dict[str, Any] | None = None,
        current_price: dict[str, Any] | None = None,
        historical_prices: list[dict[str, Any]] | None = None,
        news: list[dict[str, Any]] | None = None,
        portfolio: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, str]]:
        context = {
            "company": company,
            "current_price": current_price,
            "historical_prices": historical_prices,
            "news": news,
            "portfolio": portfolio,
        }
        return [
            {
                "role": "system",
                "content": ALPHAMIND_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n\n"
                    "Available data (null or empty means it was not supplied):\n"
                    f"{json.dumps(context, default=str, sort_keys=True)}"
                ),
            },
        ]

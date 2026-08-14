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
        analysis_context: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        if analysis_context is not None:
            content = (
                f"Question: {question}\n\n"
                "Structured analysis context (a null value means that "
                "data point was unavailable — do not invent a number):\n"
                f"{json.dumps(analysis_context, default=str, sort_keys=True)}"
            )
        else:
            context = {
                "company": company,
                "current_price": current_price,
                "historical_prices": historical_prices,
                "news": news,
                "portfolio": portfolio,
            }
            content = (
                f"Question: {question}\n\n"
                "Available data (null or empty means it was not supplied):\n"
                f"{json.dumps(context, default=str, sort_keys=True)}"
            )

        return [
            {
                "role": "system",
                "content": ALPHAMIND_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": content,
            },
        ]

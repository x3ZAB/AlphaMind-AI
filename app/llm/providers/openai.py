from typing import Any

import httpx

from app.llm.base import BaseLLMProvider
from app.llm.errors import LLMProviderError


class OpenAIProvider(BaseLLMProvider):
    BASE_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("An API key is required")

        if not model:
            raise ValueError("A model is required")

        self._api_key = api_key
        self.model = model
        self._client = client

    async def generate(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> str:
        payload = {
            key: value
            for key, value in kwargs.items()
            if key not in {"model", "messages"}
        }

        payload["model"] = self.model
        payload["messages"] = messages

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            if self._client is None:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.BASE_URL,
                        headers=headers,
                        json=payload,
                    )
            else:
                response = await self._client.post(
                    self.BASE_URL,
                    headers=headers,
                    json=payload,
                )

            response.raise_for_status()
            data = response.json()

        except httpx.HTTPStatusError as exc:
            raise LLMProviderError(
                f"LLM provider returned HTTP {exc.response.status_code}"
            ) from None

        except (httpx.HTTPError, ValueError):
            raise LLMProviderError(
                "LLM provider request failed"
            ) from None

        try:
            content = data["choices"][0]["message"]["content"]

        except (KeyError, IndexError, TypeError):
            raise LLMProviderError(
                "LLM provider returned an invalid response"
            ) from None

        if not isinstance(content, str):
            raise LLMProviderError(
                "LLM provider returned a non-text response"
            )

        return content.strip()
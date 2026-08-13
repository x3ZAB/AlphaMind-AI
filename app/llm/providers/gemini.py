from typing import Any

import httpx

from app.llm.base import BaseLLMProvider
from app.llm.errors import LLMProviderError


class GeminiProvider(BaseLLMProvider):
    BASE_URL = (
        "https://generativelanguage.googleapis.com/v1beta/interactions"
    )

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
        headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }

        steps: list[dict[str, Any]] = []

        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")

            if not content:
                continue

            if role == "assistant":
                steps.append(
                    {
                        "type": "model_output",
                        "content": [
                            {
                                "type": "text",
                                "text": content,
                            }
                        ],
                    }
                )
            else:
                steps.append(
                    {
                        "type": "user_input",
                        "content": [
                            {
                                "type": "text",
                                "text": content,
                            }
                        ],
                    }
                )

        payload: dict[str, Any] = {
            "model": self.model,
            "input": steps,
            "store": False,
        }

        for key, value in kwargs.items():
            if key not in {"model", "input", "store"}:
                payload[key] = value

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
            print(
                "GEMINI HTTP ERROR:",
                exc.response.status_code,
                exc.response.text,
            )

            raise LLMProviderError(
                f"LLM provider returned HTTP {exc.response.status_code}"
            ) from None

        except (httpx.HTTPError, ValueError) as exc:
            print("GEMINI REQUEST ERROR:", str(exc))

            raise LLMProviderError(
                "LLM provider request failed"
            ) from None

        try:
            response_steps = data["steps"]

            for step in response_steps:
                if step.get("type") != "model_output":
                    continue

                for content in step.get("content", []):
                    if content.get("type") != "text":
                        continue

                    text = content.get("text")

                    if isinstance(text, str):
                        return text.strip()

        except (KeyError, TypeError):
            pass

        raise LLMProviderError(
            "LLM provider returned an invalid response"
        ) from None
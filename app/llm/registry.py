from collections.abc import Callable

from app.llm.base import BaseLLMProvider
from app.llm.errors import UnknownLLMProviderError
from app.llm.providers.openai import OpenAIProvider
from app.llm.providers.gemini import GeminiProvider


ProviderFactory = Callable[..., BaseLLMProvider]


class LLMProviderRegistry:
    def __init__(
        self,
        providers: dict[str, ProviderFactory] | None = None,
    ) -> None:
        self._providers = {
            name.strip().lower(): factory
            for name, factory in (
                providers
                if providers is not None
                else {"openai": OpenAIProvider, "gemini": GeminiProvider}
            ).items()
        }



    def register(
        self,
        name: str,
        factory: ProviderFactory,
    ) -> None:
        self._providers[name.strip().lower()] = factory

    def create(
        self,
        provider: str,
        *,
        api_key: str,
        model: str,
        **kwargs,
    ) -> BaseLLMProvider:
        provider_name = provider.strip().lower()
        factory = self._providers.get(provider_name)
        if factory is None:
            raise UnknownLLMProviderError(
                f"Unknown LLM provider: {provider}"
            )

        return factory(
            api_key=api_key,
            model=model,
            **kwargs,
        )

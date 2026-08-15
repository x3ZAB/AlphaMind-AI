from typing import Any

from app.llm.base import LLMStepResponse, ToolDefinition
from app.llm.manager import LLMManager
from app.llm.registry import LLMProviderRegistry
from app.models.llm_configuration import UserLLMConfiguration
from app.security.encryption import EncryptionService


class ConfiguredLLMService:
    def __init__(
        self,
        encryption_service: EncryptionService | None = None,
        registry: LLMProviderRegistry | None = None,
    ) -> None:
        self.encryption_service = encryption_service or EncryptionService()
        self.registry = registry or LLMProviderRegistry()

    async def generate(
        self,
        configuration: UserLLMConfiguration,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        api_key = self.encryption_service.decrypt(
            configuration.encrypted_api_key
        )
        provider = self.registry.create(
            configuration.provider,
            api_key=api_key,
            model=configuration.model,
        )
        return await LLMManager(provider).generate(messages, **kwargs)

    async def generate_step(
        self,
        configuration: UserLLMConfiguration,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        interaction_id: str | None = None,
        **kwargs: Any,
    ) -> LLMStepResponse:
        api_key = self.encryption_service.decrypt(
            configuration.encrypted_api_key
        )
        provider = self.registry.create(
            configuration.provider,
            api_key=api_key,
            model=configuration.model,
        )
        manager = LLMManager(provider)
        return await manager.generate_step(
            messages,
            tools=tools,
            interaction_id=interaction_id,
            **kwargs,
        )

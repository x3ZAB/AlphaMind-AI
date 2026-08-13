from app.repositories.llm_configuration import LLMConfigurationRepository
from app.security.encryption import EncryptionService


class LLMConfigurationService:
    def __init__(
        self,
        repository: LLMConfigurationRepository,
        encryption_service: EncryptionService,
    ) -> None:
        self.repository = repository
        self.encryption_service = encryption_service

    def save_configuration(
        self,
        user_id: int,
        provider: str,
        model: str,
        api_key: str,
    ):
        provider = provider.strip().lower()
        model = model.strip()
        api_key = api_key.strip()

        if not provider:
            raise ValueError("Provider is required")

        if not model:
            raise ValueError("Model is required")

        if not api_key:
            raise ValueError("API key is required")

        encrypted_api_key = self.encryption_service.encrypt(api_key)

        return self.repository.create_or_update(
            user_id=user_id,
            provider=provider,
            encrypted_api_key=encrypted_api_key,
            model=model,
        )
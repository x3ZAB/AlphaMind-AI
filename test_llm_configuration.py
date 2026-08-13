from cryptography.fernet import Fernet

from app.core.config import settings
from app.models import User, UserLLMConfiguration
from app.repositories.llm_configuration import LLMConfigurationRepository
from app.security.encryption import EncryptionService
from app.services.llm_configuration import LLMConfigurationService


def test_save_configuration():
    settings.ENCRYPTION_KEY = Fernet.generate_key().decode()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    engine = create_engine("sqlite:///:memory:")
    from app.database.base import Base

    Base.metadata.create_all(engine)

    with Session(engine) as db:
        user = User(telegram_id="123")
        db.add(user)
        db.commit()

        service = LLMConfigurationService(
            repository=LLMConfigurationRepository(db),
            encryption_service=EncryptionService(),
        )

        api_key = "test-secret-key"

        configuration = service.save_configuration(
            user_id=user.id,
            provider="OpenAI",
            model="gpt-test",
            api_key=api_key,
        )

        assert configuration.provider == "openai"
        assert configuration.model == "gpt-test"

        # API key must NOT be stored as plaintext
        assert configuration.encrypted_api_key != api_key

        # It must decrypt back to the original value
        decrypted = EncryptionService().decrypt(
            configuration.encrypted_api_key
        )

        assert decrypted == api_key

        print("LLM configuration test passed")
        print("Provider normalized: OK")
        print("API key encrypted: OK")
        print("API key decrypts correctly: OK")


if __name__ == "__main__":
    test_save_configuration()
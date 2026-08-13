from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UserLLMConfiguration


class LLMConfigurationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_user_id(
        self,
        user_id: int,
    ) -> UserLLMConfiguration | None:
        statement = select(UserLLMConfiguration).where(
            UserLLMConfiguration.user_id == user_id
        )

        return self.db.scalar(statement)

    def create_or_update(
        self,
        user_id: int,
        provider: str,
        model: str,
        encrypted_api_key: str,
    ) -> UserLLMConfiguration:
        configuration = self.get_by_user_id(user_id)

        if configuration is None:
            configuration = UserLLMConfiguration(
                user_id=user_id,
                provider=provider,
                model=model,
                encrypted_api_key=encrypted_api_key,
            )
            self.db.add(configuration)
        else:
            configuration.provider = provider
            configuration.model = model
            configuration.encrypted_api_key = encrypted_api_key

        self.db.commit()
        self.db.refresh(configuration)

        return configuration
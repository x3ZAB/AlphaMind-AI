from cryptography.fernet import Fernet

from app.core.config import settings


class EncryptionService:
    def __init__(self) -> None:
        self.fernet = Fernet(settings.ENCRYPTION_KEY)

    def encrypt(self, value: str) -> str:
        return self.fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return self.fernet.decrypt(value.encode()).decode()
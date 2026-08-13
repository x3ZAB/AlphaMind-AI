from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_telegram_id(self, telegram_id: str) -> User | None:
        statement = select(User).where(
            User.telegram_id == str(telegram_id)
        )

        return self.db.scalar(statement)

    def get_or_create_by_telegram_id(
        self,
        telegram_id: str,
        username: str | None = None,
    ) -> User:
        normalized_telegram_id = str(telegram_id)
        user = self.get_by_telegram_id(normalized_telegram_id)
        if user is not None:
            return user

        user = User(
            telegram_id=normalized_telegram_id,
            username=username,
        )
        self.db.add(user)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            existing = self.get_by_telegram_id(normalized_telegram_id)
            if existing is None:
                raise
            return existing

        self.db.refresh(user)
        return user

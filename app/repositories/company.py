from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company


class CompanyRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, ticker: str, name: str) -> Company:
        company = Company(
            ticker=ticker.upper(),
            name=name,
        )

        self.db.add(company)
        self.db.commit()
        self.db.refresh(company)

        return company

    def get_by_id(self, company_id: int) -> Company | None:
        statement = select(Company).where(
            Company.id == company_id
        )

        return self.db.scalar(statement)

    def get_by_ticker(self, ticker: str) -> Company | None:
        statement = select(Company).where(
            Company.ticker == ticker.upper()
        )

        return self.db.scalar(statement)

    def get_all(self) -> list[Company]:
        statement = select(Company).order_by(Company.ticker)

        return list(self.db.scalars(statement).all())
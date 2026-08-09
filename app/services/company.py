from app.models import Company
from app.repositories import CompanyRepository


class CompanyService:
    def __init__(self, repository: CompanyRepository):
        self.repository = repository

    def create_company(self, ticker: str, name: str) -> Company:
        ticker = ticker.strip().upper()
        name = name.strip()

        if not ticker:
            raise ValueError("Ticker cannot be empty")

        if not name:
            raise ValueError("Company name cannot be empty")

        existing_company = self.repository.get_by_ticker(ticker)

        if existing_company:
            raise ValueError(
                f"Company with ticker '{ticker}' already exists"
            )

        return self.repository.create(
            ticker=ticker,
            name=name,
        )

    def get_company(self, company_id: int) -> Company | None:
        return self.repository.get_by_id(company_id)

    def get_company_by_ticker(
        self,
        ticker: str,
    ) -> Company | None:
        return self.repository.get_by_ticker(
            ticker.strip().upper()
        )

    def get_all_companies(self) -> list[Company]:
        return self.repository.get_all()
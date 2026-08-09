from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.repositories import CompanyRepository
from app.schemas import CompanyCreate, CompanyResponse
from app.services import CompanyService


router = APIRouter(
    prefix="/companies",
    tags=["Companies"],
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


@router.post(
    "",
    response_model=CompanyResponse,
    status_code=201,
)
def create_company(
    data: CompanyCreate,
    db: Session = Depends(get_db),
):
    service = CompanyService(
        CompanyRepository(db)
    )

    try:
        return service.create_company(
            ticker=data.ticker,
            name=data.name,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=409,
            detail=str(e),
        )


@router.get(
    "",
    response_model=list[CompanyResponse],
)
def get_companies(
    db: Session = Depends(get_db),
):
    service = CompanyService(
        CompanyRepository(db)
    )

    return service.get_all_companies()

@router.get(
    "/{company_id}",
    response_model=CompanyResponse,
)
def get_company(
    company_id: int,
    db: Session = Depends(get_db),
):
    service = CompanyService(
        CompanyRepository(db)
    )

    company = service.get_company(company_id)

    if company is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    return company
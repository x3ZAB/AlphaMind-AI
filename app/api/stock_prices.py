from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.repositories import StockPriceRepository
from app.schemas import StockPriceCreate, StockPriceResponse
from app.services import StockPriceService


router = APIRouter(
    prefix="/stock-prices",
    tags=["Stock Prices"],
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


@router.post(
    "",
    response_model=StockPriceResponse,
    status_code=201,
)
def create_stock_price(
    data: StockPriceCreate,
    db: Session = Depends(get_db),
):
    service = StockPriceService(
        StockPriceRepository(db)
    )

    try:
        return service.add_price(
            company_id=data.company_id,
            price=data.price,
            timestamp=data.timestamp,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )


@router.get(
    "/{stock_price_id}",
    response_model=StockPriceResponse,
)
def get_stock_price(
    stock_price_id: int,
    db: Session = Depends(get_db),
):
    service = StockPriceService(
        StockPriceRepository(db)
    )

    price = service.repository.get_by_id(stock_price_id)

    if price is None:
        raise HTTPException(
            status_code=404,
            detail="Stock price not found",
        )

    return price

@router.get(
    "/company/{company_id}",
    response_model=list[StockPriceResponse],
)
def get_company_prices(
    company_id: int,
    db: Session = Depends(get_db),
):
    service = StockPriceService(
        StockPriceRepository(db)
    )

    return service.get_price_history(company_id)

@router.get(
    "/company/{company_id}/latest",
    response_model=StockPriceResponse,
)
def get_latest_company_price(
    company_id: int,
    db: Session = Depends(get_db),
):
    service = StockPriceService(
        StockPriceRepository(db)
    )

    price = service.get_latest_price(company_id)

    if price is None:
        raise HTTPException(
            status_code=404,
            detail="No stock prices found for this company",
        )

    return price
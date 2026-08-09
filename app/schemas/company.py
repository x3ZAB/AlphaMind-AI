from pydantic import BaseModel, ConfigDict


class CompanyCreate(BaseModel):
    ticker: str
    name: str


class CompanyResponse(BaseModel):
    id: int
    ticker: str
    name: str

    model_config = ConfigDict(from_attributes=True)
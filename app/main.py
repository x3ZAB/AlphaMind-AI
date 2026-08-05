from fastapi import FastAPI
from app.core.config import settings

app = FastAPI(

    title=settings.APP_NAME,

    version=settings.VERSION
)

@app.get("/")
def root():
    return {
        "message": f"{settings.APP_NAME} is running version {settings.VERSION}"
    }
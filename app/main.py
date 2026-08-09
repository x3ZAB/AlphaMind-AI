from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.stock_prices import router as stock_prices_router
from app.api.companies import router as companies_router
from app.bot.telegram import create_bot


@asynccontextmanager
async def lifespan(app: FastAPI):
    bot = create_bot()

    await bot.initialize()
    await bot.start()
    await bot.updater.start_polling()

    yield

    await bot.updater.stop()
    await bot.stop()
    await bot.shutdown()


app = FastAPI(
    title="AlphaMind AI",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(companies_router)
app.include_router(stock_prices_router)


@app.get("/")
def root():
    return {
        "message": "AlphaMind AI API is running"
    }
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "AlphaMind AI"
    VERSION: str = "0.1.0"
    DEBUG: bool = True
    TELEGRAM_BOT_TOKEN: str

    
    DATABASE_URL: str

    REDIS_URL: str

    FINNHUB_API_KEY: str = ""
    FMP_API_KEY: str = ""
    FRED_API_KEY: str = ""
    NEWS_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
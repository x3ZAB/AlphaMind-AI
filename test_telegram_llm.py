import asyncio
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.llm.errors import LLMProviderError, UnknownLLMProviderError
from app.llm.service import ConfiguredLLMService
from app.models import User, UserLLMConfiguration
from app.repositories import UserRepository
from app.services.llm_analysis import LLMAnalysisService
from app.services.stock_analysis import StockAnalysisService
from app.services.telegram_analysis import (
    MissingLLMConfigurationError,
    TelegramAnalysisService,
    extract_ticker,
    is_analysis_request,
    user_facing_analysis_error,
)


class FakeStockService(StockAnalysisService):
    async def analyze_query(self, query: str) -> dict:
        return {
            "company": {
                "name": "NVIDIA",
                "ticker": query,
            },
            "quote": {
                "c": 100,
                "d": 1,
                "dp": 1,
                "h": 101,
                "l": 99,
                "o": 99,
                "pc": 99,
            },
            "context": {
                "company": {
                    "name": "NVIDIA",
                    "ticker": query,
                    "industry": "Technology",
                    "market_cap": 2100000,
                },
                "market": {
                    "price": 100,
                    "change": 1,
                    "change_percent": 1,
                    "high": 101,
                    "low": 99,
                    "open": 99,
                    "previous_close": 99,
                },
                "historical": {
                    "available": False,
                    "reason": "unavailable",
                    "count": 0,
                    "recent": [],
                },
                "metrics": {
                    "sma20": None,
                    "sma50": None,
                    "volatility": None,
                    "period_return": None,
                    "distance_from_sma20": None,
                    "distance_from_sma50": None,
                },
            },
        }


class FakeLLMService(ConfiguredLLMService):
    def __init__(
        self,
        response: str = "AI analysis response",
    ) -> None:
        self.response = response
        self.received_configuration = None
        self.received_messages = None

    async def generate(
        self,
        configuration,
        messages,
        **kwargs,
    ) -> str:
        self.received_configuration = configuration
        self.received_messages = messages
        return self.response


class FakeReplyMessage:
    def __init__(self, text: str) -> None:
        self.text = text
        self.replies = []

    async def reply_text(self, message: str) -> None:
        self.replies.append(message)


def make_user_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_existing_user_resolved_by_telegram_id() -> None:
    db = make_user_session()

    try:
        existing = User(
            telegram_id="123",
            username="existing",
        )

        db.add(existing)
        db.commit()

        resolved = UserRepository(
            db
        ).get_or_create_by_telegram_id(
            "123",
            username="new-name",
        )

        assert resolved.id == existing.id
        assert resolved.telegram_id == "123"
        assert resolved.username == "existing"
        assert db.query(User).count() == 1

    finally:
        db.close()


def test_missing_user_created_with_username() -> None:
    db = make_user_session()

    try:
        user = UserRepository(
            db
        ).get_or_create_by_telegram_id(
            456,
            username="new-user",
        )

        assert user.id is not None
        assert user.telegram_id == "456"
        assert user.username == "new-user"
        assert db.query(User).count() == 1

    finally:
        db.close()


def test_repeated_user_resolution_does_not_duplicate() -> None:
    db = make_user_session()

    try:
        repository = UserRepository(db)

        first = repository.get_or_create_by_telegram_id(
            "789"
        )

        second = repository.get_or_create_by_telegram_id(
            "789"
        )

        assert second.id == first.id
        assert db.query(User).count() == 1

    finally:
        db.close()


async def test_english_analysis_reaches_llm() -> None:
    user = User(telegram_id="123")

    user.llm_configuration = UserLLMConfiguration(
        provider="fake",
        model="test-model",
        encrypted_api_key="ciphertext",
    )

    llm = FakeLLMService()

    service = TelegramAnalysisService(
        stock_service=FakeStockService(),
        llm_service=llm,
        analysis_service=LLMAnalysisService(),
    )

    response = await service.analyze(
        user,
        "analyze NVDA",
    )

    # The raw LLM response must be returned.
    assert "AI analysis response" in response

    # Verify the LLM received the request.
    assert llm.received_messages is not None
    assert len(llm.received_messages) >= 2

    user_message = llm.received_messages[1]["content"]

    assert "NVDA" in user_message


def test_english_analysis_intent_and_ticker_identification() -> None:
    analysis_requests = {
        "analyze NVDA": "NVDA",
        "Analyze nvda": "NVDA",
        "analysis of NVDA": "NVDA",
        "What do you think about NVDA?": "NVDA",
        "What do you think about AAPL?": "AAPL",
        "Give me an analysis of Tesla": "TESLA",
        "Analyze Microsoft": "MICROSOFT",
    }

    for request, expected_ticker in analysis_requests.items():
        assert is_analysis_request(request)
        assert extract_ticker(request) == expected_ticker

    assert not is_analysis_request("NVDA")
    assert not is_analysis_request("AAPL")
    assert not is_analysis_request("Apple")
    assert not is_analysis_request("Microsoft")

    assert extract_ticker("NVDA") == "NVDA"
    assert extract_ticker("Apple") == "APPLE"
    assert extract_ticker("Microsoft") == "MICROSOFT"


async def test_analysis_handler_creates_user_and_preserves_missing_config_message() -> None:
    import app.bot.telegram as telegram

    db = make_user_session()

    original_session_local = telegram.SessionLocal

    telegram.SessionLocal = lambda: db

    class FakeUpdate:
        def __init__(self) -> None:
            self.message = FakeReplyMessage(
                "analyze NVDA"
            )

            self.effective_user = SimpleNamespace(
                id=321,
                username="first-time-user",
            )

    update = FakeUpdate()

    try:
        await telegram.analysis_message(
            update,
            "analyze NVDA",
        )

        user = (
            db.query(User)
            .filter_by(telegram_id="321")
            .one()
        )

    finally:
        telegram.SessionLocal = original_session_local
        db.close()

    assert user.username == "first-time-user"

    assert update.message.replies == [
        "Please configure your LLM provider and API key "
        "before using AI analysis."
    ]


async def test_missing_configuration_is_user_friendly() -> None:
    user = User(
        telegram_id="123"
    )

    service = TelegramAnalysisService(
        stock_service=FakeStockService(),
        llm_service=FakeLLMService(),
        analysis_service=LLMAnalysisService(),
    )

    try:
        await service.analyze(
            user,
            "حلل NVDA",
        )

    except MissingLLMConfigurationError as error:
        message = user_facing_analysis_error(error)

    else:
        raise AssertionError(
            "Missing configuration did not raise"
        )

    assert "configure" in message
    assert "API key" in message


async def test_provider_failures_are_user_friendly() -> None:
    assert "supported" in user_facing_analysis_error(
        UnknownLLMProviderError(
            "internal provider"
        )
    )

    assert "unavailable" in user_facing_analysis_error(
        LLMProviderError(
            "internal provider failure"
        )
    )


async def test_successful_response_does_not_expose_api_key() -> None:
    api_key = "super-secret-api-key"

    user = User(
        telegram_id="123"
    )

    user.llm_configuration = UserLLMConfiguration(
        provider="fake",
        model="test-model",
        encrypted_api_key=api_key,
    )

    llm = FakeLLMService(
        "Balanced analysis without credentials"
    )

    service = TelegramAnalysisService(
        stock_service=FakeStockService(),
        llm_service=llm,
        analysis_service=LLMAnalysisService(),
    )

    response = await service.analyze(
        user,
        "حلل NVDA",
    )

    # The API key must never be exposed.
    assert api_key not in response

    # The LLM response is returned to Telegram.
    assert "Balanced analysis without credentials" in response


async def test_start_help_and_plain_ticker_lookup_remain_available() -> None:
    import app.bot.telegram as telegram

    class FakeUpdate:
        def __init__(self, text: str) -> None:
            self.message = FakeReplyMessage(text)
            self.effective_user = SimpleNamespace(
                id=123
            )

    start_update = FakeUpdate("/start")

    await telegram.start(
        start_update,
        None,
    )

    assert "Welcome" in start_update.message.replies[0]

    help_update = FakeUpdate("/help")

    await telegram.help_command(
        help_update,
        None,
    )

    assert "AlphaMind AI" in help_update.message.replies[0]

    original_service = telegram.StockAnalysisService

    class PlainLookupService:
        async def analyze_query(
            self,
            query: str,
        ) -> dict:
            assert query == "NVDA"

            return {
                "company": {
                    "name": "NVIDIA",
                    "ticker": "NVDA",
                },
                "quote": {
                    "c": 100,
                    "d": 1,
                    "dp": 1,
                    "h": 101,
                    "l": 99,
                    "o": 99,
                    "pc": 99,
                },
            }

    telegram.StockAnalysisService = PlainLookupService

    db = make_user_session()
    original_session_local = telegram.SessionLocal
    telegram.SessionLocal = lambda: db

    try:
        ticker_update = FakeUpdate("NVDA")

        await telegram.stock_message(
            ticker_update,
            None,
        )

    finally:
        telegram.StockAnalysisService = original_service
        telegram.SessionLocal = original_session_local
        db.close()

    assert "NVIDIA" in ticker_update.message.replies[0]
    assert "AI analysis" not in ticker_update.message.replies[0]


async def main() -> None:
    test_existing_user_resolved_by_telegram_id()

    test_missing_user_created_with_username()

    test_repeated_user_resolution_does_not_duplicate()

    await test_analysis_handler_creates_user_and_preserves_missing_config_message()

    await test_english_analysis_reaches_llm()

    test_english_analysis_intent_and_ticker_identification()

    await test_missing_configuration_is_user_friendly()

    await test_provider_failures_are_user_friendly()

    await test_successful_response_does_not_expose_api_key()

    await test_start_help_and_plain_ticker_lookup_remain_available()

    print("Telegram LLM integration tests passed")


if __name__ == "__main__":
    asyncio.run(main())
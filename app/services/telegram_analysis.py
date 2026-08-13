import re
from dataclasses import dataclass

from app.llm.errors import LLMProviderError, UnknownLLMProviderError
from app.llm.service import ConfiguredLLMService
from app.models import User
from app.services.llm_analysis import LLMAnalysisService
from app.services.stock_analysis import StockAnalysisService


class MissingUserError(RuntimeError):
    pass


class MissingLLMConfigurationError(RuntimeError):
    pass


@dataclass
class TelegramAnalysisService:
    stock_service: StockAnalysisService
    llm_service: ConfiguredLLMService
    analysis_service: LLMAnalysisService

    async def analyze(
        self,
        user: User | None,
        request: str,
    ) -> str:
        if user is None:
            raise MissingUserError

        configuration = user.llm_configuration
        if configuration is None:
            raise MissingLLMConfigurationError

        ticker_query = extract_ticker(request)
        if ticker_query is None:
            raise ValueError("No company or ticker found")

        stock_data = await self.stock_service.analyze_query(ticker_query)
        if stock_data is None:
            raise LookupError("Company or ticker not found")

        messages = self.analysis_service.build_messages(
            question=request,
            company=stock_data.get("company"),
            current_price=stock_data.get("quote"),
        )
        return await self.llm_service.generate(configuration, messages)


ANALYSIS_PATTERNS = (
    re.compile(r"^analyze\s+(?P<target>.+)$", re.IGNORECASE),
    re.compile(r"^analysis\s+of\s+(?P<target>.+)$", re.IGNORECASE),
    re.compile(
        r"^what\s+do\s+you\s+think\s+about\s+(?P<target>.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^give\s+me\s+an\s+analysis\s+of\s+(?P<target>.+)$",
        re.IGNORECASE,
    ),
)


def _analysis_target(text: str) -> str | None:
    normalized = text.strip().rstrip("?!.")
    for pattern in ANALYSIS_PATTERNS:
        match = pattern.match(normalized)
        if match:
            return match.group("target").strip()
    return None


def is_analysis_request(text: str) -> bool:
    return _analysis_target(text) is not None


def extract_ticker(text: str) -> str | None:
    target = _analysis_target(text) or text.strip().rstrip("?!.")
    if not target:
        return None

    words = target.split()
    candidate = words[-1].strip(".,!?;:")
    if candidate and candidate.isascii() and candidate.isalpha():
        return candidate.upper()

    return None


def user_facing_analysis_error(error: Exception) -> str:
    if isinstance(error, MissingUserError):
        return "I couldn't identify your Telegram account. Please try again."
    if isinstance(error, MissingLLMConfigurationError):
        return (
            "Please configure your LLM provider and API key "
            "before using AI analysis."
        )
    if isinstance(error, UnknownLLMProviderError):
        return "Your configured LLM provider is not supported yet."
    if isinstance(error, LLMProviderError):
        return "The AI analysis service is temporarily unavailable. Please try again."
    if isinstance(error, LookupError):
        return "I couldn't find a company or ticker for that analysis request."
    if isinstance(error, ValueError):
        return "Please include a company name or ticker, such as: حلل NVDA"
    return "I couldn't complete the AI analysis. Please try again."

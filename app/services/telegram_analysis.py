import re
from dataclasses import dataclass, field
from typing import Any

from app.agent.agent import AIAgent
from app.llm.errors import LLMProviderError, UnknownLLMProviderError
from app.llm.service import ConfiguredLLMService
from app.models import User
from app.services.llm_analysis import LLMAnalysisService
from app.services.stock_analysis import StockAnalysisService
from app.tools.registry import ToolRegistry
from app.tools.stock import GetCompanyTool, GetStockPriceTool, SearchCompanyTool


class MissingUserError(RuntimeError):
    pass


class MissingLLMConfigurationError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _format_number(
    value: Any,
    decimals: int = 2,
) -> str:
    if value is None:
        return "N/A"

    try:
        return f"{float(value):,.{decimals}f}"
    except (TypeError, ValueError):
        return "N/A"


def _format_percent(
    value: Any,
    decimals: int = 2,
) -> str:
    if value is None:
        return "N/A"

    try:
        return f"{float(value) * 100:.{decimals}f}%"
    except (TypeError, ValueError):
        return "N/A"


def _format_market_cap(value: Any) -> str:
    if value is None:
        return "N/A"

    try:
        value = float(value)

        # Finnhub market capitalization is provided in millions USD.
        if value >= 1_000_000:
            return f"${value / 1_000_000:.2f}T"

        if value >= 1_000:
            return f"${value / 1_000:.2f}B"

        return f"${value:.2f}M"

    except (TypeError, ValueError):
        return "N/A"


def _clean_llm_text(text: str) -> str:
    """
    Clean excessive markdown formatting while preserving readable text.
    """
    if not text:
        return ""

    text = str(text).strip()

    # Remove markdown heading markers.
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)

    # Normalize markdown bullets.
    text = re.sub(r"^[*•]\s+", "• ", text, flags=re.MULTILINE)

    # Remove excessive blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ---------------------------------------------------------------------------
# Telegram analysis service
# ---------------------------------------------------------------------------


@dataclass
class TelegramAnalysisService:
    llm_service: ConfiguredLLMService
    tool_registry: ToolRegistry = field(default_factory=ToolRegistry)
    stock_service: StockAnalysisService | None = None
    analysis_service: LLMAnalysisService | None = None
    agent: AIAgent | None = None

    def __post_init__(self) -> None:
        if self.stock_service is not None:
            provider = getattr(self.stock_service, "provider", None)
            stock_tool = GetStockPriceTool(provider=provider, stock_service=self.stock_service)
            company_tool = GetCompanyTool(provider=provider)
            search_tool = SearchCompanyTool(provider=provider)
            self.tool_registry = ToolRegistry([stock_tool, company_tool, search_tool])

        if self.agent is None:
            self.agent = AIAgent(
                llm_service=self.llm_service,
                tool_registry=self.tool_registry,
            )

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

        return await self.agent.run(configuration, request)


# ---------------------------------------------------------------------------
# Analysis request parsing
# ---------------------------------------------------------------------------


ANALYSIS_PATTERNS = (
    re.compile(
        r"^analyze\s+(?P<target>.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^analysis\s+of\s+(?P<target>.+)$",
        re.IGNORECASE,
    ),
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

    if (
        candidate
        and candidate.isascii()
        and candidate.isalpha()
    ):
        return candidate.upper()

    return None


# ---------------------------------------------------------------------------
# User-facing errors
# ---------------------------------------------------------------------------


def user_facing_analysis_error(error: Exception) -> str:
    if isinstance(error, MissingUserError):
        return (
            "I couldn't identify your Telegram account. "
            "Please try again."
        )

    if isinstance(error, MissingLLMConfigurationError):
        return (
            "Please configure your LLM provider and API key "
            "before using AI analysis."
        )

    if isinstance(error, UnknownLLMProviderError):
        return (
            "Your configured LLM provider is not supported yet."
        )

    if isinstance(error, LLMProviderError):
        return (
            "The AI analysis service is temporarily unavailable. "
            "Please try again."
        )

    if isinstance(error, LookupError):
        return (
            "I couldn't find a company or ticker "
            "for that analysis request."
        )

    if isinstance(error, ValueError):
        return (
            "Please include a company name or ticker, "
            "such as: analyze NVDA"
        )

    return (
        "I couldn't complete the AI analysis. "
        "Please try again."
    )
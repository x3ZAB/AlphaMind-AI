import re
from dataclasses import dataclass, field
from typing import Any

from app.agent.agent import AIAgent
from app.llm.errors import LLMProviderError, UnknownLLMProviderError
from app.llm.service import ConfiguredLLMService
from app.models import User
from app.services.conversation_context import context_manager
from app.services.llm_analysis import LLMAnalysisService
from app.services.stock_analysis import StockAnalysisService
from app.tools.registry import ToolRegistry
from app.tools.stock import (
    GetCompanyTool,
    GetStockPriceTool,
    SearchCompanyTool,
)
from app.bot.formatters.financial import (
    FinancialMessageFormatter,
    normalize_markdown,
)


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
    if not text:
        return ""

    text = str(text).strip()

    # Remove markdown heading markers.
    text = re.sub(
        r"^#{1,6}\s*",
        "",
        text,
        flags=re.MULTILINE,
    )

    # Normalize markdown bullets.
    text = re.sub(
        r"^[*•]\s+",
        "• ",
        text,
        flags=re.MULTILINE,
    )

    # Remove excessive blank lines.
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()


# ---------------------------------------------------------------------------
# Telegram analysis service
# ---------------------------------------------------------------------------


@dataclass
class TelegramAnalysisService:
    llm_service: ConfiguredLLMService
    tool_registry: ToolRegistry = field(
        default_factory=ToolRegistry
    )
    stock_service: StockAnalysisService | None = None
    analysis_service: LLMAnalysisService | None = None
    agent: AIAgent | None = None

    def __post_init__(self) -> None:
        if self.stock_service is not None:
            provider = getattr(
                self.stock_service,
                "provider",
                None,
            )

            stock_tool = GetStockPriceTool(
                provider=provider,
                stock_service=self.stock_service,
            )

            company_tool = GetCompanyTool(
                provider=provider,
            )

            search_tool = SearchCompanyTool(
                provider=provider,
            )

            self.tool_registry = ToolRegistry(
                [
                    stock_tool,
                    company_tool,
                    search_tool,
                ]
            )

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

        # One stable conversation/session key per user.
        session_key = str(
            getattr(user, "telegram_id", None)
            or getattr(user, "id", "default_session")
        )

        # ---------------------------------------------------------------
        # Resolve ONLY explicit ticker symbols.
        #
        # IMPORTANT:
        # Natural language is NOT parsed here.
        # The LLM receives the context and understands it.
        # ---------------------------------------------------------------

        resolved_request, context = (
            context_manager.resolve_references(
                request,
                session_key,
            )
        )

        # ---------------------------------------------------------------
        # Build context for the LLM.
        # ---------------------------------------------------------------

        base_system_prompt = getattr(
            self.agent,
            "system_prompt",
            "",
        )

        system_prompt = base_system_prompt

        context_lines: list[str] = []

        if context.active_ticker:
            context_lines.append(
                "Active Stock: "
                f"{context.active_ticker}"
                f" ({context.active_company or context.active_ticker})"
            )

        if context.comparison_pair:
            context_lines.append(
                "Current Comparison Pair: "
                f"{context.comparison_pair[0]} (first) "
                f"vs "
                f"{context.comparison_pair[1]} (second)"
            )

        if context.recent_tickers:
            context_lines.append(
                "Recently Mentioned Tickers: "
                + ", ".join(context.recent_tickers)
            )

        if context.history:
            context_lines.append(
                "Recent Conversation History:"
            )

            for turn in context.history[-4:]:
                context_lines.append(
                    f"User: {turn['user']}\n"
                    f"Assistant: {turn['assistant']}"
                )

        if context_lines:
            context_block = (
                "\n\n"
                "[CONVERSATION CONTEXT & HISTORY]\n"
                + "\n".join(context_lines)
                + "\n"
                "[END CONVERSATION CONTEXT]\n\n"
            )

            context_block += (
                "CONTEXT INSTRUCTIONS:\n"
                "- Use the conversation context to understand "
                "natural-language references.\n"
                "- The user may refer to a stock using words such as "
                "'it', 'this stock', 'that company', "
                "'the first one', or 'the second one'.\n"
                "- Determine what those references mean from the "
                "conversation context.\n"
                "- Do NOT require predefined keywords to understand "
                "the user's intent.\n"
                "- Do NOT assume that every uppercase word is a ticker.\n"
                "- If the context is genuinely insufficient, ask the "
                "user for clarification.\n"
            )

            if "[CONVERSATION CONTEXT & HISTORY]" not in system_prompt:
                system_prompt += context_block

        # ---------------------------------------------------------------
        # Create agent with the context-aware system prompt.
        # ---------------------------------------------------------------

        active_agent = AIAgent(
            llm_service=self.llm_service,
            tool_registry=self.tool_registry,
            system_prompt=system_prompt,
            max_rounds=getattr(
                self.agent,
                "max_rounds",
                5,
            ),
        )

        # ---------------------------------------------------------------
        # Let the LLM / agent understand the request.
        # ---------------------------------------------------------------

        raw_response = await active_agent.run(
            configuration,
            resolved_request,
        )

        # ---------------------------------------------------------------
        # IMPORTANT:
        #
        # Do NOT inspect the LLM response for tickers.
        #
        # Context must be updated from USER input only.
        # Otherwise the assistant's own response can accidentally
        # modify the conversation state.
        # ---------------------------------------------------------------

        explicit_user_tickers = (
            context_manager.extract_tickers_from_text(
                request
            )
        )

        if len(explicit_user_tickers) == 1:
            ticker = explicit_user_tickers[0]

            # The context should already have this ticker from
            # resolve_references(), but keep this defensive update.
            if context.active_ticker != ticker:
                context.set_active(ticker)

        elif len(explicit_user_tickers) >= 2:
            context.set_comparison(
                explicit_user_tickers[0],
                explicit_user_tickers[1],
            )

        # Store the conversational turn.
        context.add_turn(
            request,
            raw_response,
        )

        # ---------------------------------------------------------------
        # Format response.
        # ---------------------------------------------------------------

        formatter = FinancialMessageFormatter()

        if formatter.is_conversational(
            raw_response,
            request,
        ):
            return normalize_markdown(raw_response)

        return formatter.format_financial_text(
            raw_response,
            query=request,
        )


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


def _analysis_target(
    text: str,
) -> str | None:

    normalized = (
        text.strip()
        .rstrip("?!.")
    )

    for pattern in ANALYSIS_PATTERNS:
        match = pattern.match(normalized)

        if match:
            return match.group("target").strip()

    return None


def is_analysis_request(
    text: str,
) -> bool:
    return _analysis_target(text) is not None


def extract_ticker(
    text: str,
) -> str | None:
    target = (
        _analysis_target(text)
        or text.strip().rstrip("?!.")
    )

    if not target:
        return None

    words = target.split()
    candidate = words[-1].strip(".,!?;:")

    if candidate and candidate.isascii() and candidate.isalpha():
        return candidate.upper()

    return None


# ---------------------------------------------------------------------------
# User-facing errors
# ---------------------------------------------------------------------------


def user_facing_analysis_error(
    error: Exception,
) -> str:

    if isinstance(error, MissingUserError):
        return (
            "I couldn't identify your Telegram account. "
            "Please try again."
        )

    if isinstance(
        error,
        MissingLLMConfigurationError,
    ):
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

    return (
        "I couldn't complete the analysis right now. "
        "Please try again."
    )
import re
from dataclasses import dataclass, field
from typing import Any

COMPANY_NAME_TO_TICKER = {
    "NVIDIA": "NVDA",
    "NVIDIA CORPORATION": "NVDA",
    "إنفيديا": "NVDA",
    "APPLE": "AAPL",
    "آبل": "AAPL",
    "ابل": "AAPL",
    "MICROSOFT": "MSFT",
    "مايكروسوفت": "MSFT",
    "TESLA": "TSLA",
    "تسلا": "TSLA",
    "AMAZON": "AMZN",
    "أمازون": "AMZN",
    "AMAZON.COM": "AMZN",
    "APPLIED OPTOELECTRONICS": "AAOI",
    "IREN": "IREN",
    "ZETA": "ZETA",
    "ZETA GLOBAL": "ZETA",
}

@dataclass
class ConversationContext:
    active_ticker: str | None = None
    active_company: str | None = None
    recent_tickers: list[str] = field(default_factory=list)
    comparison_pair: list[str] = field(default_factory=list)
    history: list[dict[str, str]] = field(default_factory=list)

    def set_active(self, ticker: str, company: str | None = None) -> None:
        t = ticker.upper()
        self.active_ticker = t
        if t not in self.comparison_pair:
            self.comparison_pair = []  # Clear previous comparison pair on active stock switch
        if company:
            self.active_company = company
        else:
            self.active_company = f"{t} Corporation"

        if t not in self.recent_tickers:
            self.recent_tickers.append(t)
            if len(self.recent_tickers) > 5:
                self.recent_tickers.pop(0)

    def add_ticker(self, ticker: str, company: str | None = None) -> None:
        self.set_active(ticker, company=company)

    def set_comparison(self, ticker1: str, ticker2: str) -> None:
        t1, t2 = ticker1.upper(), ticker2.upper()
        self.comparison_pair = [t1, t2]
        self.set_active(t1)
        self.set_active(t2)

    def add_turn(self, user_msg: str, assistant_msg: str) -> None:
        self.history.append({"user": user_msg, "assistant": assistant_msg})
        if len(self.history) > 6:
            self.history.pop(0)


class ConversationContextManager:
    """
    Manages in-memory conversation context state per user/session key.
    """

    def __init__(self) -> None:
        self._contexts: dict[str, ConversationContext] = {}

    def get_context(self, session_key: str) -> ConversationContext:
        if session_key not in self._contexts:
            self._contexts[session_key] = ConversationContext()
        return self._contexts[session_key]

    def reset_context(self, session_key: str) -> None:
        if session_key in self._contexts:
            del self._contexts[session_key]

    def extract_tickers_from_text(self, text: str) -> list[str]:
        """Extract explicit ticker symbols or recognized company names from text in order of appearance."""
        text_upper = text.upper()
        matches: list[tuple[int, str]] = []

        # 1. Match recognized company names (Arabic or English) and record start position
        for name, ticker in COMPANY_NAME_TO_TICKER.items():
            pos = 0
            while True:
                idx = text_upper.find(name, pos)
                if idx == -1:
                    break
                matches.append((idx, ticker))
                pos = idx + len(name)

        # 2. Match standalone ASCII 2-5 char uppercase words
        for match in re.finditer(r"\b[A-Z]{2,5}\b", text):
            w_upper = match.group(0)
            matches.append((match.start(), w_upper))

        # Sort all matches by start position in text
        matches.sort(key=lambda x: x[0])

        found: list[str] = []
        for _, ticker in matches:
            if ticker not in found:
                found.append(ticker)

        return found

    def resolve_references(self, request: str, session_key: str) -> tuple[str, ConversationContext]:
        """
        Retrieves context and updates active tickers if explicit tickers exist in current message.
        Returns a tuple of (request_string, conversation_context).
        """
        context = self.get_context(session_key)
        req_clean = request.strip()

        explicit_tickers = self.extract_tickers_from_text(req_clean)
        if len(explicit_tickers) >= 2:
            context.set_comparison(explicit_tickers[0], explicit_tickers[1])
        elif len(explicit_tickers) == 1:
            if context.active_ticker and explicit_tickers[0] != context.active_ticker and any(kw in req_clean.lower() for kw in ["compare", "vs", "versus", "قارن"]):
                context.set_comparison(context.active_ticker, explicit_tickers[0])
            else:
                context.set_active(explicit_tickers[0])

        return req_clean, context


# Global singleton instance
context_manager = ConversationContextManager()

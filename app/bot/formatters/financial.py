import re
from typing import Any

DIVIDER = "━━━━━━━━━━━━━━━━━━"

ENGLISH_DISCLAIMER = "⚠️ Not financial advice."
ARABIC_DISCLAIMER = "⚠️ ليست نصيحة مالية."

# Regex to detect Arabic characters
ARABIC_REGEX = re.compile(r"[\u0600-\u06FF]")

# Conversational queries that should maintain natural response format
CONVERSATIONAL_PATTERNS = [
    re.compile(r"^(hi|hello|hey|greetings|good\s+(morning|afternoon|evening)|who\s+are\s+you|what\s+can\s+you\s+do|thanks|thank\s+you)[\.!\?]?$", re.IGNORECASE),
    re.compile(r"^(مرحبا|أهلا|سلام|صباح\s+الخير|مساء\s+الخير|من\s+أنت|ماذا\s+تفعل|شكرا)[\.!\?]?$", re.IGNORECASE),
]

FINANCIAL_INDICATORS = {
    "price", "stock", "market", "ticker", "sma", "volatility",
    "valuation", "risk", "analysis", "compare", "quote", "high",
    "low", "open", "prev close", "market cap", "$", "%",
    "سعر", "سهم", "أسهم", "سوق", "تذبذب", "مخاطر", "تحليل", "مقارنة"
}


def is_arabic(text: str) -> bool:
    """Check if the text contains Arabic characters."""
    return bool(ARABIC_REGEX.search(text))


def convert_markdown_tables(text: str) -> str:
    """
    Convert raw Markdown tables (e.g., | Symbol | Price |) into a clean,
    stacked vertical layout suitable for mobile messaging.
    """
    lines = text.split("\n")
    new_lines = []
    in_table = False
    headers: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            # Table separator line like |---|---|
            if re.match(r"^\|[\s:\|-]+\|$", stripped):
                continue
            cells = [c.strip() for c in stripped.split("|")[1:-1]]

            if not in_table:
                in_table = True
                headers = cells
                continue

            # Row entry
            if headers and len(cells) == len(headers):
                first_cell = cells[0]
                new_lines.append(f"\n🏢 {first_cell}")
                for h, v in zip(headers[1:], cells[1:]):
                    if v:
                        new_lines.append(f"• {h}: {v}")
            else:
                row_str = " - ".join(f"{h}: {v}" for h, v in zip(headers, cells) if v)
                new_lines.append(f"• {row_str}")
        else:
            if in_table:
                in_table = False
                headers = []
                new_lines.append("")
            new_lines.append(line)

    return "\n".join(new_lines)


def normalize_markdown(text: str) -> str:
    """
    Normalize markdown text by converting raw tables, stripping markdown heading markers,
    standardizing bullet points, and cleaning excessive blank lines.
    """
    if not text:
        return ""

    # Convert tables if present
    if "|" in text and "\n|" in text:
        text = convert_markdown_tables(text)

    # Remove markdown heading markers (# Header -> Header)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)

    # Normalize markdown bullets (* or - -> •)
    text = re.sub(r"^[*•-]\s+", "• ", text, flags=re.MULTILINE)

    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


class FinancialMessageFormatter:
    """
    A provider-independent formatter responsible for converting financial/AI responses
    into Telegram-friendly, clean, compact, and profssional messages.
    """

    def __init__(self, max_length: int = 3800) -> None:
        self.max_length = max_length

    def is_conversational(self, text: str, query: str = "") -> bool:
        """
        Determine whether a query/response is conversational (e.g. 'hi')
        rather than a financial dashboard or stock analysis.
        """
        clean_q = query.strip().lower()
        for pattern in CONVERSATIONAL_PATTERNS:
            if pattern.match(clean_q):
                return True

        # Check if the query is a simple general question without financial terms
        if clean_q in {"hi", "hello", "hey", "who are you", "what can you do", "مرحبا", "أهلا"}:
            return True

        # If text is short and has no financial keywords/symbols
        clean_text = text.lower()
        has_financial_sign = any(kw in clean_text for kw in FINANCIAL_INDICATORS)
        if len(text) < 200 and not has_financial_sign:
            return True

        return False

    def format_stock_price(
        self,
        name: str,
        ticker: str,
        price: float | str,
        change_text: str | None = None,
        high: float | str | None = None,
        low: float | str | None = None,
        open_price: float | str | None = None,
        previous_close: float | str | None = None,
        is_arabic_lang: bool = False,
    ) -> str:
        """Format a clean, compact stock price response."""
        title = f"🍎 {name} ({ticker})" if ticker.upper() == "AAPL" else f"📊 {name} ({ticker})"
        
        if is_arabic_lang:
            header_price = "💰 السعر"
            header_change = "📈 التغير"
            header_market = "📊 بيانات السوق"
            label_high = "الأعلى"
            label_low = "الأدنى"
            label_open = "الافتتاح"
            label_pc = "الإغلاق السابق"
            disclaimer = ARABIC_DISCLAIMER
        else:
            header_price = "💰 PRICE"
            header_change = "📈 CHANGE"
            header_market = "📊 MARKET DATA"
            label_high = "High"
            label_low = "Low"
            label_open = "Open"
            label_pc = "Prev Close"
            disclaimer = ENGLISH_DISCLAIMER

        sections = [title, DIVIDER, f"{header_price}\n${price}"]

        if change_text:
            sections.append(f"{header_change}\n{change_text}")

        market_details = []
        if high is not None:
            market_details.append(f"{label_high}: ${high}")
        if low is not None:
            market_details.append(f"{label_low}: ${low}")
        if open_price is not None:
            market_details.append(f"{label_open}: ${open_price}")
        if previous_close is not None:
            market_details.append(f"{label_pc}: ${previous_close}")

        if market_details:
            sections.append(f"{header_market}\n" + "\n".join(market_details))

        sections.append(DIVIDER)
        sections.append(disclaimer)

        return "\n\n".join(sections)

    def format_financial_text(self, text: str, query: str = "") -> str:
        """
        Structure an AI financial response into clean sections with consistent AlphaMind styling.
        """
        normalized = normalize_markdown(text)
        is_arb = is_arabic(text) or is_arabic(query)
        disclaimer = ARABIC_DISCLAIMER if is_arb else ENGLISH_DISCLAIMER

        # If already formatted with divider, just ensure disclaimer present
        if DIVIDER in normalized:
            if disclaimer not in normalized:
                normalized = normalized.rstrip() + f"\n\n{DIVIDER}\n{disclaimer}"
            return normalized

        # Parse sections or wrap in AlphaMind style
        lines = [line.strip() for line in normalized.split("\n") if line.strip()]
        if not lines:
            return text

        title_line = ""
        # Check if first line looks like a title/ticker line
        first_line = lines[0]
        if any(marker in first_line for marker in ["(", ")", "NVIDIA", "Apple", "Microsoft", "NVDA", "AAPL", "MSFT", "Analysis", "تحليل"]):
            title_line = first_line
            body_lines = lines[1:]
        else:
            body_lines = lines

        formatted_parts = []
        if title_line:
            if not title_line.startswith("📊") and not title_line.startswith("🍎"):
                title_line = f"📊 {title_line}"
            formatted_parts.append(title_line)
        else:
            formatted_parts.append("📊 AlphaMind AI Analysis")

        formatted_parts.append(DIVIDER)

        # Process body content into sections
        current_section = []
        for line in body_lines:
            # Check if line looks like a section header (all caps, or ending with colon)
            if (
                line.isupper()
                or line.endswith(":")
                or any(kw in line.lower() for kw in ["market data", "technicals", "analysis", "risks", "summary", "verdict", "comparison", "بيانات", "فني", "مخاطر", "ملخص"])
            ) and len(line) < 50 and not line.startswith("•"):
                if current_section:
                    formatted_parts.append("\n".join(current_section))
                    current_section = []
                
                # Add appropriate emoji to header if missing
                header_text = line.rstrip(":")
                if not any(emoji in header_text for emoji in ["💰", "📊", "📈", "🧠", "⚠️", "🎯", "⚖️", "🏢", "💵", "📦", "🔥"]):
                    if any(k in header_text.lower() for k in ["budget", "investment", "ميزانية", "مبلغ"]):
                        header_text = f"💵 {header_text}"
                    elif any(k in header_text.lower() for k in ["shares", "approx. shares", "عدد الأسهم"]):
                        header_text = f"📦 {header_text}"
                    elif any(k in header_text.lower() for k in ["price", "market", "سعر", "بيانات"]):
                        header_text = f"💰 {header_text}"
                    elif any(k in header_text.lower() for k in ["technical", "sma", "فني"]):
                        header_text = f"📈 {header_text}"
                    elif any(k in header_text.lower() for k in ["risk", "مخاطر"]):
                        header_text = f"⚠️ {header_text}"
                    elif any(k in header_text.lower() for k in ["verdict"]):
                        header_text = f"🧠 {header_text}"
                    elif any(k in header_text.lower() for k in ["summary", "view", "takeaway", "ملخص", "تقييم", "نظرة"]):
                        header_text = f"🎯 {header_text}"
                    elif any(k in header_text.lower() for k in ["why", "reasons", "أسباب", "اسباب"]):
                        header_text = f"🔥 {header_text}"
                    elif any(k in header_text.lower() for k in ["compare", "comparison", "vs", "مقارنة"]):
                        header_text = f"⚖️ {header_text}"
                    else:
                        header_text = f"🧠 {header_text}"
                current_section.append(header_text)
            else:
                current_section.append(line)

        if current_section:
            formatted_parts.append("\n".join(current_section))

        formatted_parts.append(DIVIDER)
        formatted_parts.append(disclaimer)

        return "\n\n".join(formatted_parts)

    def split_message(self, text: str) -> list[str]:
        """
        Safely split long formatted text into message chunks under max_length,
        preserving section boundaries, markdown formatting, and disclaimer on the final chunk.
        """
        if len(text) <= self.max_length:
            return [text]

        chunks: list[str] = []
        lines = text.split("\n")
        current_chunk: list[str] = []
        current_len = 0

        for line in lines:
            line_len = len(line) + 1  # +1 for newline
            if current_len + line_len > self.max_length:
                if current_chunk:
                    chunks.append("\n".join(current_chunk).strip())
                    current_chunk = []
                    current_len = 0

                # Handle single line longer than max_length
                if line_len > self.max_length:
                    words = line.split(" ")
                    for word in words:
                        if current_len + len(word) + 1 > self.max_length:
                            chunks.append("\n".join(current_chunk).strip())
                            current_chunk = [word]
                            current_len = len(word) + 1
                        else:
                            current_chunk.append(word)
                            current_len += len(word) + 1
                    continue

            current_chunk.append(line)
            current_len += line_len

        if current_chunk:
            chunks.append("\n".join(current_chunk).strip())

        is_arb = is_arabic(text)
        disclaimer = ARABIC_DISCLAIMER if is_arb else ENGLISH_DISCLAIMER
        if disclaimer in text and disclaimer not in chunks[-1]:
            if len(chunks[-1]) + len(disclaimer) + 25 <= self.max_length:
                chunks[-1] = chunks[-1] + f"\n\n{DIVIDER}\n{disclaimer}"
            else:
                chunks.append(f"{DIVIDER}\n{disclaimer}")

        return chunks

    def format(self, text: str, query: str = "") -> list[str]:
        """
        Main entry point: Formats input response text into clean Telegram message chunks.
        """
        if not text:
            return [""]

        if self.is_conversational(text, query):
            clean_conv = normalize_markdown(text)
            return self.split_message(clean_conv)

        # Apply financial dashboard formatting
        formatted = self.format_financial_text(text, query)
        return self.split_message(formatted)

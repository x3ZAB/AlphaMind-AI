import asyncio

from app.bot.formatters.financial import (
    ARABIC_DISCLAIMER,
    ENGLISH_DISCLAIMER,
    FinancialMessageFormatter,
    convert_markdown_tables,
    is_arabic,
    normalize_markdown,
)


def test_normal_conversational_response() -> None:
    formatter = FinancialMessageFormatter()
    
    # Simple greeting query
    res = formatter.format("Hello! How can I help you today with your investments?", query="hi")
    assert len(res) == 1
    assert "Hello!" in res[0]
    assert ENGLISH_DISCLAIMER not in res[0]
    assert "📊 MARKET DATA" not in res[0]

    # Conversational explanation
    res2 = formatter.format("I am AlphaMind AI, your financial market assistant.", query="who are you?")
    assert len(res2) == 1
    assert "AlphaMind AI" in res2[0]
    assert ENGLISH_DISCLAIMER not in res2[0]


def test_stock_price_response() -> None:
    formatter = FinancialMessageFormatter()
    formatted = formatter.format_stock_price(
        name="Apple Inc.",
        ticker="AAPL",
        price=305.93,
        change_text="+$3.01 (+0.99%)",
        high=307.00,
        low=302.50,
        open_price=303.00,
        previous_close=302.92,
    )
    assert "🍎 Apple Inc. (AAPL)" in formatted
    assert "💰 PRICE" in formatted
    assert "$305.93" in formatted
    assert "📈 CHANGE" in formatted
    assert "+$3.01 (+0.99%)" in formatted
    assert ENGLISH_DISCLAIMER in formatted


def test_stock_analysis_response() -> None:
    formatter = FinancialMessageFormatter()
    raw_analysis = (
        "NVIDIA Corporation (NVDA)\n\n"
        "MARKET DATA\n"
        "Price: $141.98\n"
        "Change: +$0.58 (+0.41%)\n\n"
        "TECHNICALS\n"
        "SMA 50: $125.75\n"
        "Volatility: 2.39%\n\n"
        "AI ANALYSIS\n"
        "NVIDIA is showing strong momentum in data centers and AI accelerators.\n\n"
        "RISKS\n"
        "* High valuation\n"
        "* Geopolitical exposure\n\n"
        "SUMMARY\n"
        "Strong fundamentals but monitor high valuation."
    )
    chunks = formatter.format(raw_analysis, query="Analyze NVDA")
    assert len(chunks) == 1
    formatted = chunks[0]

    assert "📊 NVIDIA Corporation (NVDA)" in formatted
    assert "💰 MARKET DATA" in formatted
    assert "📈 TECHNICALS" in formatted
    assert "🧠 AI ANALYSIS" in formatted
    assert "⚠️ RISKS" in formatted
    assert "• High valuation" in formatted
    assert "🎯 SUMMARY" in formatted
    assert ENGLISH_DISCLAIMER in formatted


def test_stock_comparison_response() -> None:
    formatter = FinancialMessageFormatter()
    raw_comparison = (
        "MSFT vs IREN Comparison\n\n"
        "| Symbol | Company | Price | Change |\n"
        "| --- | --- | --- | --- |\n"
        "| MSFT | Microsoft | $415.20 | +1.2% |\n"
        "| IREN | IREN Ltd | $8.50 | -0.4% |\n\n"
        "COMPARISON\n"
        "MSFT is a mature tech leader, while IREN focuses on Bitcoin mining and AI cloud data centers.\n\n"
        "AI VERDICT\n"
        "MSFT offers steady growth, while IREN presents higher risk and reward."
    )
    chunks = formatter.format(raw_comparison, query="Compare MSFT and IREN")
    assert len(chunks) == 1
    formatted = chunks[0]

    assert "MSFT" in formatted
    assert "IREN" in formatted
    assert "🏢 MSFT" in formatted
    assert "🏢 IREN" in formatted
    assert "⚖️ COMPARISON" in formatted
    assert "🧠 AI VERDICT" in formatted
    assert ENGLISH_DISCLAIMER in formatted


def test_arabic_stock_analysis() -> None:
    formatter = FinancialMessageFormatter()
    raw_arabic = (
        "NVIDIA Corporation (NVDA)\n\n"
        "بيانات السوق:\n"
        "السعر: $141.98\n"
        "التغير: +$0.58 (+0.41%)\n\n"
        "التحليل الفني:\n"
        "SMA 50: $125.75\n"
        "التذبذب: 2.39%\n\n"
        "التحليل:\n"
        "تظهر شركة إنفيديا زخماً قرياً في مراكز البيانات.\n\n"
        "المخاطر:\n"
        "* التقييم المرتفع\n"
        "* المنافسة\n\n"
        "الملخص:\n"
        "أداء قوي مع ضرورة متابعة التقييم."
    )
    chunks = formatter.format(raw_arabic, query="حلل NVDA")
    assert len(chunks) == 1
    formatted = chunks[0]

    assert "NVIDIA Corporation (NVDA)" in formatted
    assert "💰 بيانات السوق" in formatted
    assert "📈 التحليل الفني" in formatted
    assert "🧠 التحليل" in formatted
    assert "⚠️ المخاطر" in formatted
    assert "• التقييم المرتفع" in formatted
    assert "🎯 الملخص" in formatted
    assert ARABIC_DISCLAIMER in formatted


def test_long_response_splitting() -> None:
    formatter = FinancialMessageFormatter(max_length=500)
    long_text = "📊 NVIDIA Corporation (NVDA)\n\n" + ("Section content line with financial info. " * 30) + f"\n\n{ENGLISH_DISCLAIMER}"
    chunks = formatter.split_message(long_text)
    
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 500
    
    # Title on first chunk
    assert "📊 NVIDIA Corporation (NVDA)" in chunks[0]
    # Disclaimer on last chunk
    assert ENGLISH_DISCLAIMER in chunks[-1]


def test_markdown_normalization() -> None:
    raw = "### Analysis Header\n\n* Point one\n* Point two\n\n| Col1 | Col2 |\n|---|---|\n| A | B |\n"
    normalized = normalize_markdown(raw)
    assert "###" not in normalized
    assert "Analysis Header" in normalized
    assert "• Point one" in normalized
    assert "• Point two" in normalized
    assert "🏢 A" in normalized
    assert "• Col2: B" in normalized


def test_missing_market_data_formatting() -> None:
    formatter = FinancialMessageFormatter()
    raw = "NVIDIA Corporation (NVDA)\n\nMarket data is currently unavailable for this symbol."
    chunks = formatter.format(raw, query="Analyze NVDA")
    assert len(chunks) == 1
    assert "unavailable" in chunks[0]
    assert ENGLISH_DISCLAIMER in chunks[0]


def test_disclaimer_preservation() -> None:
    formatter = FinancialMessageFormatter()
    res_en = formatter.format_financial_text("AAPL Stock Analysis", query="Analyze AAPL")
    assert ENGLISH_DISCLAIMER in res_en

    res_ar = formatter.format_financial_text("تحليل سهم NVDA", query="حلل NVDA")
    assert ARABIC_DISCLAIMER in res_ar


def main() -> None:
    test_normal_conversational_response()
    test_stock_price_response()
    test_stock_analysis_response()
    test_stock_comparison_response()
    test_arabic_stock_analysis()
    test_long_response_splitting()
    test_markdown_normalization()
    test_missing_market_data_formatting()
    test_disclaimer_preservation()
    print("Financial message formatter tests passed successfully!")


if __name__ == "__main__":
    main()

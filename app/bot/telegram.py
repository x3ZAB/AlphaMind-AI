from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.core.config import settings
from app.services.stock_analysis import StockAnalysisService


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "Welcome to AlphaMind AI! 🚀\n\n"
        "Just send me a stock name or ticker.\n\n"
        "Examples:\n"
        "AAPL\n"
        "Apple\n"
        "NVIDIA\n"
        "Microsoft"
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "🤖 AlphaMind AI\n\n"
        "Just send me the stock you're interested in.\n\n"
        "Examples:\n"
        "• AAPL\n"
        "• Apple\n"
        "• NVIDIA\n"
        "• Microsoft"
    )


async def stock_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.message.text.strip()

    if not query:
        return

    try:
        service = StockAnalysisService()

        result = await service.analyze_query(query)

        if result is None:
            await update.message.reply_text(
                f"❌ I couldn't find a stock matching:\n"
                f"\"{query}\"\n\n"
                "Try a company name or ticker like AAPL, Apple, or NVIDIA."
            )
            return

        company = result["company"]
        quote = result["quote"]

        if not quote or not quote.get("c"):
            await update.message.reply_text(
                f"⚠️ I found {company.get('name', query)}, "
                "but there is no current market data available."
            )
            return

        name = company.get("name", "Unknown")
        ticker = company.get("ticker", "N/A")

        price = quote.get("c")
        change = quote.get("d")
        change_percent = quote.get("dp")
        high = quote.get("h")
        low = quote.get("l")
        open_price = quote.get("o")
        previous_close = quote.get("pc")

        if change is not None and change_percent is not None:
            if change >= 0:
                trend = "📈"
                change_text = f"+{change} (+{change_percent}%)"
            else:
                trend = "📉"
                change_text = f"{change} ({change_percent}%)"
        else:
            trend = "📊"
            change_text = "N/A"

        message = (
            f"📊 {name}\n\n"
            f"🏷️ Ticker: {ticker}\n"
            f"💰 Price: ${price}\n"
            f"{trend} Change: {change_text}\n\n"
            f"🔺 High: ${high}\n"
            f"🔻 Low: ${low}\n"
            f"🌅 Open: ${open_price}\n"
            f"📌 Previous Close: ${previous_close}"
        )

        await update.message.reply_text(message)

    except Exception:
        await update.message.reply_text(
            "❌ Something went wrong while getting the stock data.\n"
            "Please try again."
        )


def create_bot() -> Application:
    application = (
        Application.builder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            stock_message,
        )
    )

    return application
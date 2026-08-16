import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.core.config import settings
from app.database.session import SessionLocal
from app.llm.service import ConfiguredLLMService
from app.repositories import (
    LLMConfigurationRepository,
    UserRepository,
)
from app.security.encryption import EncryptionService
from app.services.llm_configuration import LLMConfigurationService
from app.services.stock_analysis import StockAnalysisService
from app.services.telegram_analysis import (
    TelegramAnalysisService,
    is_analysis_request,
    user_facing_analysis_error,
)

logger = logging.getLogger(__name__)


SETTINGS_PROVIDER = 1
SETTINGS_MODEL = 2
SETTINGS_API_KEY = 3


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
        "• Microsoft\n\n"
        "Use /settings to configure your LLM."
    )


async def settings_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "⚙️ LLM Settings\n\n"
        "Enter your provider.\n\n"
        "Currently supported:\n"
        "• openai\n"
        "• gemini"
    )

    return SETTINGS_PROVIDER


async def settings_provider(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    provider = update.message.text.strip().lower()

    if provider not in {"openai", "gemini"}:
        await update.message.reply_text(
            "❌ Unsupported provider.\n\n"
            "Currently supported: openai, gemini"
        )
        return SETTINGS_PROVIDER

    context.user_data["llm_provider"] = provider

    if provider == "gemini":
        model_example = "gemini-3.1-flash-lite"
    else:
        model_example = "gpt-4.1-mini"

    await update.message.reply_text(
        "Enter the model name.\n\n"
        "Example:\n"
        f"{model_example}"
    )

    return SETTINGS_MODEL


async def settings_model(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    model = update.message.text.strip()

    if not model:
        await update.message.reply_text(
            "❌ Model cannot be empty.\n"
            "Please enter the model name."
        )
        return SETTINGS_MODEL

    context.user_data["llm_model"] = model

    provider = context.user_data.get(
        "llm_provider",
        "openai",
    )

    provider_name = provider.capitalize()

    await update.message.reply_text(
        f"🔐 Now send your {provider_name} API key.\n\n"
        "It will be encrypted before being stored.\n\n"
        "Use /cancel to cancel."
    )

    return SETTINGS_API_KEY


async def settings_api_key(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    api_key = update.message.text.strip()

    if not api_key:
        await update.message.reply_text(
            "❌ API key cannot be empty."
        )
        return SETTINGS_API_KEY

    telegram_user = update.effective_user

    if telegram_user is None:
        await update.message.reply_text(
            "❌ Could not identify your Telegram account."
        )
        return ConversationHandler.END

    db = SessionLocal()

    try:
        user = UserRepository(db).get_or_create_by_telegram_id(
            str(telegram_user.id),
            username=telegram_user.username,
        )

        provider = context.user_data.get("llm_provider")
        model = context.user_data.get("llm_model")

        if not provider:
            raise ValueError("LLM provider is missing")

        if not model:
            raise ValueError("LLM model is missing")

        service = LLMConfigurationService(
            repository=LLMConfigurationRepository(db),
            encryption_service=EncryptionService(),
        )

        service.save_configuration(
            user_id=user.id,
            provider=provider,
            model=model,
            api_key=api_key,
        )

        await update.message.reply_text(
            "✅ LLM configuration saved successfully.\n\n"
            "You can now try:\n"
            "analyze NVDA"
        )

    except Exception as error:
        logger.exception(
            "LLM configuration save failed: %s",
            type(error).__name__,
        )

        await update.message.reply_text(
            "❌ Failed to save LLM configuration.\n"
            "Please check the server logs."
        )

    finally:
        context.user_data.pop("llm_provider", None)
        context.user_data.pop("llm_model", None)
        db.close()

    return ConversationHandler.END


async def settings_cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    context.user_data.pop("llm_provider", None)
    context.user_data.pop("llm_model", None)

    await update.message.reply_text(
        "❌ LLM configuration cancelled."
    )

    return ConversationHandler.END


async def stock_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    query = update.message.text.strip()

    if not query:
        return

    telegram_user = update.effective_user
    telegram_id = getattr(telegram_user, "id", None)

    db = SessionLocal()
    has_llm_config = False
    try:
        if telegram_id is not None:
            user = UserRepository(db).get_or_create_by_telegram_id(
                str(telegram_id),
            )
            if user and user.llm_configuration:
                has_llm_config = True
    finally:
        db.close()

    if is_analysis_request(query) or has_llm_config:
        await analysis_message(update, query)
        return

    try:
        service = StockAnalysisService()

        result = await service.analyze_query(query)

        if result is None:
            await update.message.reply_text(
                f"❌ I couldn't find a stock matching:\n"
                f'"{query}"\n\n'
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


async def analysis_message(
    update: Update,
    request: str,
):
    telegram_user = update.effective_user
    telegram_id = getattr(telegram_user, "id", None)
    username = getattr(telegram_user, "username", None)

    db = SessionLocal()

    try:
        user = None

        if telegram_id is not None:
            user = UserRepository(db).get_or_create_by_telegram_id(
                str(telegram_id),
                username=username,
            )

        # Log diagnostic info without exposing secrets.
        if user and user.llm_configuration:
            config = user.llm_configuration
            logger.info(
                "Analysis request: telegram_id=%s provider=%s model=%s "
                "has_encrypted_key=%s",
                telegram_id,
                config.provider,
                config.model,
                bool(config.encrypted_api_key),
            )

            # Verify decryption works without logging the key value.
            try:
                decrypted = EncryptionService().decrypt(
                    config.encrypted_api_key
                )
                logger.info(
                    "API key decryption: success, key_length=%d",
                    len(decrypted),
                )
            except Exception as decrypt_error:
                logger.error(
                    "API key decryption FAILED: %s: %s",
                    type(decrypt_error).__name__,
                    str(decrypt_error),
                )
        else:
            logger.info(
                "Analysis request: telegram_id=%s has_config=%s",
                telegram_id,
                bool(user and user.llm_configuration),
            )

        service = TelegramAnalysisService(
            llm_service=ConfiguredLLMService(
                EncryptionService()
            ),
        )

        response = await service.analyze(
            user,
            request,
        )

        from app.bot.formatters.financial import FinancialMessageFormatter

        formatter = FinancialMessageFormatter()
        chunks = formatter.split_message(response)
        for chunk in chunks:
            await update.message.reply_text(chunk)

    except Exception as error:
        logger.exception(
            "Analysis failed for telegram_id=%s request=%r: %s: %s",
            telegram_id,
            request,
            type(error).__name__,
            str(error),
        )
        await update.message.reply_text(
            user_facing_analysis_error(error)
        )

    finally:
        db.close()


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

    settings_handler = ConversationHandler(
        entry_points=[
            CommandHandler(
                "settings",
                settings_start,
            ),
        ],
        states={
            SETTINGS_PROVIDER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    settings_provider,
                )
            ],
            SETTINGS_MODEL: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    settings_model,
                )
            ],
            SETTINGS_API_KEY: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    settings_api_key,
                )
            ],
        },
        fallbacks=[
            CommandHandler(
                "cancel",
                settings_cancel,
            ),
        ],
    )

    application.add_handler(settings_handler)

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            stock_message,
        )
    )

    return application

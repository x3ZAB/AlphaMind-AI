from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from app.core.config import settings


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to AlphaMind AI! 🚀"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Available commands:\n"
        "/start - Start AlphaMind AI\n"
        "/help - Show available commands"
    )


def create_bot() -> Application:
    application = Application.builder().token(
        settings.TELEGRAM_BOT_TOKEN
    ).build()

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    return application
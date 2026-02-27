#!/usr/bin/env python3
import logging
import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8544623193:AAGB5p8qqnkPbsmolPkKVpAGW7XmWdmFOak"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Hotmail Checker Bot Started!\n/check - Check accounts\n/help - Show help")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📖 Available Commands:\n/start - Start the bot\n/check - Check Hotmail accounts\n/help - Show this message")

async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Checker is running... Send combo file path")


def main():
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("check", check_command))
        logger.info("✅ Bot started successfully!")
        application.run_polling()
    except Exception as e:
        logger.error(f"❌ Error starting bot: {e}")
        raise


if __name__ == '__main__':
    main()
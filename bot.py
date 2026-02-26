import os
import logging
import threading
import asyncio
import time
import shutil
import glob
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# Import tools
import flux
import h
import hit
import p7
import pullerv2
import database

# Authorized Admin ID
ADMIN_ID = 5944410248
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8544623193:AAGB5p8qqnkPbsmolPkKVpAGW7XmWdmFOak")

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

UPLOADS_DIR = "uploads"
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Helper for presentation
def get_footer():
    return f"\n\n💎 Credits to Admin [{ADMIN_ID}]"

def restricted(func):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if not database.is_approved(user_id):
            await update.message.reply_text(f"❌ Access Denied. You are not authorized.\nContact Admin [{ADMIN_ID}] for access.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

def admin_only(func):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if not database.is_admin(user_id):
            await update.message.reply_text("❌ This command is restricted to Admin only.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    credits = database.get_credits(user_id)

    keyboard = [
        [InlineKeyboardButton("🎮 Flux Scraper", callback_data='tool_flux')],
        [InlineKeyboardButton("📧 Hotmail Checker (H)", callback_data='tool_h')],
        [InlineKeyboardButton("🔥 Advanced Hotmail (HIT)", callback_data='tool_hit')],
        [InlineKeyboardButton("💰 Rewards Points (P7)", callback_data='tool_p7')],
        [InlineKeyboardButton("🗝 Code Puller (V2)", callback_data='tool_pullerv2')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = (
        f"🚀 **ToolBot Dashboard**\n\n"
        f"👤 User: `{user_id}`\n"
        f"💳 Credits: `{credits}`\n\n"
        f"Please select a tool to start:{get_footer()}"
    )
    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode='Markdown')

@admin_only
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_id = int(context.args[0])
        database.set_approved(target_id, True)
        await update.message.reply_text(f"✅ User `{target_id}` approved.")
    except:
        await update.message.reply_text("Usage: `/approve <id>`")

@admin_only
async def add_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
        database.add_credits(target_id, amount)
        await update.message.reply_text(f"✅ Added {amount} credits to `{target_id}`.")
    except:
        await update.message.reply_text("Usage: `/add_credits <id> <amount>`")

@admin_only
async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_users = database.get_all_users()
    if not all_users:
        await update.message.reply_text("No users found.")
        return

    report = "👥 **User List:**\n\n"
    for uid, data in all_users.items():
        status = "✅" if data.get("approved") else "❌"
        report += f"ID: `{uid}` | {status} | Credits: `{data.get('credits', 0)}`\n"

    await update.message.reply_text(report, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith('tool_'):
        tool = query.data.split('_')[1]
        context.user_data['selected_tool'] = tool
        await query.edit_message_text(
            text=f"✅ Tool `{tool.upper()}` selected.\n\n"
                 f"Now, please upload your `.txt` combo file.{get_footer()}",
            parse_mode='Markdown'
        )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not database.is_approved(user_id):
        return

    selected_tool = context.user_data.get('selected_tool')
    if not selected_tool:
        await update.message.reply_text("❌ Please select a tool first using /start.")
        return

    if database.get_credits(user_id) <= 0:
        await update.message.reply_text("❌ You don't have enough credits. Contact Admin.")
        return

    document = update.message.document
    if not document.file_name.lower().endswith('.txt'):
        await update.message.reply_text("❌ Please upload a valid `.txt` file.")
        return

    file = await context.bot.get_file(document.file_id)
    file_path = os.path.join(UPLOADS_DIR, f"{user_id}_{int(time.time())}_{document.file_name}")
    await file.download_to_drive(file_path)

    status_message = await update.message.reply_text(f"⏳ File received. Initializing `{selected_tool.upper()}`...")

    # Deduct 1 credit
    database.deduct_credit(user_id)

    # Use application's shared session/loop
    threading.Thread(
        target=run_tool_async,
        args=(selected_tool, file_path, update.effective_chat.id, status_message.message_id, context.application),
        daemon=True
    ).start()

def run_tool_async(tool_name, file_path, chat_id, status_msg_id, application):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    last_update_time = [0]
    update_interval = 5

    def bot_callback(text):
        now = time.time()
        if now - last_update_time[0] < update_interval and "Finished" not in text and "Completed" not in text:
            return
        last_update_time[0] = now

        asyncio.run_coroutine_threadsafe(
            application.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg_id,
                text=f"⚙️ **[{tool_name.upper()}]**\n{text}{get_footer()}",
                parse_mode='Markdown'
            ),
            application.loop
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
            pullerv2.phase2_validate_codes(accounts, codes=None, callback=bot_callback)
            results_folders = glob.glob("validation_results_*")
            if results_folders:
                results_path = max(results_folders, key=os.path.getmtime)

        asyncio.run_coroutine_threadsafe(
            application.bot.send_message(chat_id=chat_id, text=f"✅ Tool `{tool_name.upper()}` finished execution!"),
            application.loop
        )

        if results_path and os.path.exists(results_path):
            if os.path.isdir(results_path):
                zip_name = f"{results_path}_{int(time.time())}"
                shutil.make_archive(zip_name, 'zip', results_path)
                final_file = f"{zip_name}.zip"
            else:
                final_file = results_path

            asyncio.run_coroutine_threadsafe(
                application.bot.send_document(chat_id=chat_id, document=open(final_file, 'rb')),
                application.loop
            )

    except Exception as e:
        logger.error(f"Error in {tool_name}: {e}", exc_info=True)
        asyncio.run_coroutine_threadsafe(
            application.bot.send_message(chat_id=chat_id, text=f"❌ Error in `{tool_name.upper()}`: {str(e)}"),
            application.loop
        )
    finally:
        loop.close()

if __name__ == '__main__':
    # Add initial admin if needed
    if not database.is_approved(ADMIN_ID):
        database.set_approved(ADMIN_ID, True)

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('approve', approve))
    application.add_handler(CommandHandler('add_credits', add_credits))
    application.add_handler(CommandHandler('users', users))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("Bot started...")
    application.run_polling()

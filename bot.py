import os
import logging
import threading
import asyncio
import time
import shutil
import glob
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ParseMode

# Import tools
import flux
import h
import hit
import p7
import pullerv2
import database

# Authorized Admin ID
ADMIN_ID = 5944410248
# Fallback token if env var is missing
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8544623193:AAGB5p8qqnkPbsmolPkKVpAGW7XmWdmFOak")

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

UPLOADS_DIR = "uploads"
os.makedirs(UPLOADS_DIR, exist_ok=True)

# --- UI Helpers ---

def get_footer():
    return f"\n\n✨ _Credits to Admin_ [`{ADMIN_ID}`]"

def get_header(title):
    return f"🛡 **{title}**\n━━━━━━━━━━━━━━━━━━━━\n"

def restricted(func):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_user:
            return
        user_id = update.effective_user.id
        if not database.is_approved(user_id):
            await update.message.reply_text(
                f"🚫 **Access Denied**\n\nYou are not authorized to use this bot. "
                f"Please contact the Administrator to request access.\n\n"
                f"Your ID: `{user_id}`{get_footer()}",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

def admin_only(func):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_user:
            return
        user_id = update.effective_user.id
        if not database.is_admin(user_id):
            await update.message.reply_text(
                f"❌ **Admin Only**\n\nThis command is restricted to the bot owner.{get_footer()}",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- Command Handlers ---

@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    credits = database.get_credits(user_id)
    settings = database.get_user_settings(user_id)

    keyboard = [
        [InlineKeyboardButton("🎮 Flux Scraper", callback_data='tool_flux'),
         InlineKeyboardButton("📧 Hotmail (H)", callback_data='tool_h')],
        [InlineKeyboardButton("🔥 Adv. Hotmail (HIT)", callback_data='tool_hit'),
         InlineKeyboardButton("💰 Rewards (P7)", callback_data='tool_p7')],
        [InlineKeyboardButton("🗝 Code Puller (V2)", callback_data='tool_pullerv2')],
        [InlineKeyboardButton("⚙️ Settings", callback_data='settings'),
         InlineKeyboardButton("👤 Profile", callback_data='profile')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    msg = (
        f"{get_header('TOOLBOT DASHBOARD')}"
        f"Welcome back! Your account is active.\n\n"
        f"💳 **Credits:** `{credits}`\n"
        f"🧵 **Threads:** `{settings['threads']}`\n"
        f"🌐 **Proxy:** `{settings['proxy'] if settings['proxy'] else 'None'}`\n\n"
        f"Select a tool to begin:{get_footer()}"
    )
    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

@restricted
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_admin = database.is_admin(user_id)

    help_text = (
        f"{get_header('HELP & COMMANDS')}"
        f"/start - Dashboard\n"
        f"/threads <num> - Set execution threads\n"
        f"/proxy <url> - Set proxy (http://user:pass@host:port)\n"
        f"/proxy none - Remove proxy\n"
        f"/me - Check credits & status\n"
        f"/help - Show this message\n\n"
        f"**Limits:**\n"
        f"• Max 5 threads without proxy.\n"
        f"• Max 100 threads with proxy."
    )

    if is_admin:
        help_text += (
            f"\n\n**Admin Commands:**\n"
            f"/approve `<id>` - Approve a user\n"
            f"/add_credits `<id> <amount>` - Give credits\n"
            f"/users - List all users"
        )

    help_text += get_footer()
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

@restricted
async def threads_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    settings = database.get_user_settings(user_id)

    if not context.args:
        await update.message.reply_text(f"🧵 **Current Threads:** `{settings['threads']}`\nUsage: `/threads <num>`")
        return

    try:
        num = int(context.args[0])
        if num < 1: raise ValueError

        if not settings['proxy'] and num > 5 and not database.is_admin(user_id):
            await update.message.reply_text("❌ **Thread Limit!**\n\nYou can only use max **5 threads** without a proxy.")
            return

        if num > 100 and not database.is_admin(user_id):
            num = 100

        database.update_user_settings(user_id, threads=num)
        await update.message.reply_text(f"✅ **Threads updated to:** `{num}`")
    except:
        await update.message.reply_text("❌ Invalid number.")

@restricted
async def proxy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        settings = database.get_user_settings(user_id)
        proxy = settings['proxy'] if settings['proxy'] else "None"
        await update.message.reply_text(f"🌐 **Current Proxy:** `{proxy}`\nUsage: `/proxy <url>` or `/proxy none`")
        return

    proxy_url = context.args[0].lower()
    if proxy_url == 'none':
        database.update_user_settings(user_id, proxy="")
        # Also reset threads if they were > 5
        settings = database.get_user_settings(user_id)
        if settings['threads'] > 5 and not database.is_admin(user_id):
             database.update_user_settings(user_id, threads=5)
             await update.message.reply_text("✅ Proxy removed. Threads reset to 5.")
        else:
             await update.message.reply_text("✅ Proxy removed.")
    else:
        # Simple validation
        if not (proxy_url.startswith('http') or proxy_url.startswith('socks')):
             await update.message.reply_text("❌ Invalid proxy format. Use `http://...` or `socks5://...`")
             return
        database.update_user_settings(user_id, proxy=proxy_url)
        await update.message.reply_text(f"✅ **Proxy updated to:** `{proxy_url}`")

@restricted
async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    credits = database.get_credits(user_id)
    settings = database.get_user_settings(user_id)
    status = "Admin" if database.is_admin(user_id) else "Approved User"

    msg = (
        f"{get_header('USER PROFILE')}"
        f"🆔 **User ID:** `{user_id}`\n"
        f"🏅 **Status:** `{status}`\n"
        f"💳 **Credits:** `{credits}`\n"
        f"🧵 **Threads:** `{settings['threads']}`\n"
        f"🌐 **Proxy:** `{settings['proxy'] if settings['proxy'] else 'None'}`{get_footer()}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

# --- Admin Handlers ---

@admin_only
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_id = int(context.args[0])
        database.set_approved(target_id, True)
        await update.message.reply_text(f"✅ **User Approved**\n\nID `{target_id}` can now use the bot.", parse_mode=ParseMode.MARKDOWN)
    except:
        await update.message.reply_text("💡 **Usage:** `/approve <user_id>`", parse_mode=ParseMode.MARKDOWN)

@admin_only
async def add_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
        database.add_credits(target_id, amount)
        await update.message.reply_text(f"💰 **Credits Added**\n\nAdded `{amount}` credits to `{target_id}`.", parse_mode=ParseMode.MARKDOWN)
    except:
        await update.message.reply_text("💡 **Usage:** `/add_credits <user_id> <amount>`", parse_mode=ParseMode.MARKDOWN)

@admin_only
async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_users = database.get_all_users()
    if not all_users:
        await update.message.reply_text("📂 **No users registered.**", parse_mode=ParseMode.MARKDOWN)
        return

    report = f"{get_header('REGISTERED USERS')}"
    for uid, data in all_users.items():
        status = "✅" if data.get("approved") else "❌"
        report += f"• ID: `{uid}` | {status} | `{data.get('credits', 0)}` cr | `{data.get('threads', 5)}` th\n"

    await update.message.reply_text(report, parse_mode=ParseMode.MARKDOWN)

# --- Message & Callback Handlers ---

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query: return
    await query.answer()

    user_id = query.from_user.id
    if not database.is_approved(user_id):
        return

    if query.data.startswith('tool_'):
        tool = query.data.split('_')[1]
        context.user_data['selected_tool'] = tool
        await query.edit_message_text(
            text=f"{get_header(f'TOOL SELECTED: {tool.upper()}')}"
                 f"Please upload your **.txt combo file** now.\n\n"
                 f"Note: This will cost `1` credit.{get_footer()}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_start')]])
        )
    elif query.data == 'settings':
        settings = database.get_user_settings(user_id)
        msg = (
            f"{get_header('SETTINGS')}"
            f"🧵 **Threads:** `{settings['threads']}`\n"
            f"🌐 **Proxy:** `{settings['proxy'] if settings['proxy'] else 'None'}`\n\n"
            f"Use commands to change:\n"
            f"• `/threads <num>`\n"
            f"• `/proxy <url>`"
        )
        await query.edit_message_text(
            text=msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_start')]])
        )
    elif query.data == 'profile':
        credits = database.get_credits(user_id)
        status = "Admin" if database.is_admin(user_id) else "Approved User"
        await query.edit_message_text(
            text=f"{get_header('USER PROFILE')}"
                 f"🆔 **User ID:** `{user_id}`\n"
                 f"🏅 **Status:** `{status}`\n"
                 f"💳 **Credits:** `{credits}`{get_footer()}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_start')]])
        )
    elif query.data == 'back_to_start':
        credits = database.get_credits(user_id)
        settings = database.get_user_settings(user_id)
        keyboard = [
            [InlineKeyboardButton("🎮 Flux Scraper", callback_data='tool_flux'),
             InlineKeyboardButton("📧 Hotmail (H)", callback_data='tool_h')],
            [InlineKeyboardButton("🔥 Adv. Hotmail (HIT)", callback_data='tool_hit'),
             InlineKeyboardButton("💰 Rewards (P7)", callback_data='tool_p7')],
            [InlineKeyboardButton("🗝 Code Puller (V2)", callback_data='tool_pullerv2')],
            [InlineKeyboardButton("⚙️ Settings", callback_data='settings'),
             InlineKeyboardButton("👤 Profile", callback_data='profile')]
        ]
        await query.edit_message_text(
            text=f"{get_header('TOOLBOT DASHBOARD')}"
                 f"Select a tool below to begin execution:\n\n"
                 f"💳 **Credits:** `{credits}`\n"
                 f"🧵 **Threads:** `{settings['threads']}`{get_footer()}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user: return
    user_id = update.effective_user.id
    if not database.is_approved(user_id):
        return

    selected_tool = context.user_data.get('selected_tool')
    if not selected_tool:
        await update.message.reply_text("⚠️ **No tool selected.**\n\nPlease select a tool from the dashboard first.", parse_mode=ParseMode.MARKDOWN)
        return

    if database.get_credits(user_id) <= 0:
        await update.message.reply_text("🚫 **Insufficient Credits**\n\nYou need at least `1` credit to run a tool.", parse_mode=ParseMode.MARKDOWN)
        return

    document = update.message.document
    if not document or not document.file_name.lower().endswith('.txt'):
        await update.message.reply_text("❌ **Invalid File**\n\nPlease upload a valid `.txt` combo file.", parse_mode=ParseMode.MARKDOWN)
        return

    file = await context.bot.get_file(document.file_id)
    file_path = os.path.join(UPLOADS_DIR, f"{user_id}_{int(time.time())}_{document.file_name}")
    await file.download_to_drive(file_path)

    settings = database.get_user_settings(user_id)

    status_message = await update.message.reply_text(
        f"🔄 **Initializing `{selected_tool.upper()}`...**\n"
        f"File: `{document.file_name}`\n"
        f"Threads: `{settings['threads']}`\n"
        f"Proxy: `{settings['proxy'] if settings['proxy'] else 'None'}`\n\n"
        f"🚀 _Starting engines..._",
        parse_mode=ParseMode.MARKDOWN
    )

    # Deduct 1 credit
    database.deduct_credit(user_id)

    # Use application's loop to update Telegram from worker thread
    threading.Thread(
        target=run_tool_async,
        args=(selected_tool, file_path, update.effective_chat.id, status_message.message_id, context.application, settings),
        daemon=True
    ).start()

# --- Tool Execution Engine ---

def run_tool_async(tool_name, file_path, chat_id, status_msg_id, application, user_settings):
    last_update_time = [0]
    update_interval = 5
    threads = user_settings['threads']
    proxy = user_settings['proxy']

    def bot_callback(text):
        now = time.time()
        if now - last_update_time[0] < update_interval and "Finished" not in text and "Completed" not in text:
            return
        last_update_time[0] = now

        asyncio.run_coroutine_threadsafe(
            application.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg_id,
                text=f"⚙️ **TOOL IN PROGRESS: {tool_name.upper()}**\n━━━━━━━━━━━━━━━━━━━━\n{text}{get_footer()}",
                parse_mode=ParseMode.MARKDOWN
            ),
            application.loop
        )

    # Immediate start message
    bot_callback("🚀 Execution started... Loading accounts.")

    try:
        results_path = None
        if tool_name == 'flux':
            parser = flux.ComboParser(file_path)
            accounts = parser.parse()
            if not accounts:
                bot_callback("❌ No valid accounts found in file.")
                return
            settings = flux.Settings()
            settings.set('max_threads', threads)
            # flux has internal proxy manager, but we can try to inject if needed
            scraper = flux.MultiPlatformScraper(accounts, settings, "All", log_callback=bot_callback)
            scraper.check_all()
            results_path = scraper.results_folder

        elif tool_name == 'h':
            checker = h.HotmailChecker(log_callback=bot_callback)
            checker.run(file_path, num_threads=threads)
            results_path = "Hotmail-Hits.txt"

        elif tool_name == 'hit':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = [l.strip() for l in f.readlines() if ':' in l]
            if not lines:
                bot_callback("❌ No valid accounts found in file.")
                return
            stats = hit.LiveStats(len(lines), callback=bot_callback)
            result_mgr = hit.EnhancedResultManager(f"bot_{int(time.time())}", "full")

            def process_hit(line):
                try:
                    email, password = line.split(':', 1)
                    checker = hit.UnifiedChecker(check_mode="full_enhanced")
                    # Inject proxy if set
                    if proxy:
                         checker.session.proxies = {'http': proxy, 'https': proxy}
                    res = checker.check(email.strip(), password.strip())
                    stats.update(res["status"], res if res["status"] == "HIT" else None)
                    if res["status"] == "HIT":
                        result_mgr.save_hit(email, password, res)
                    stats.print_live("full_enhanced")
                except: pass

            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=threads) as executor:
                executor.map(process_hit, lines)
            results_path = result_mgr.base_folder

        elif tool_name == 'p7':
            p7.check_bulk(file_path, threads=threads, proxy=proxy, callback=bot_callback)
            results_path = "Results"

        elif tool_name == 'pullerv2':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                accounts = []
                for line in f:
                    if ':' in line:
                        accounts.append(line.strip().split(':', 1))
            if not accounts:
                bot_callback("❌ No valid accounts found in file.")
                return
            # pullerv2 has its own proxy manager in pullerv2.py, but it's hardcoded to read proxies.txt
            # For simplicity, we just run it as is for now or could inject
            pullerv2.MAX_THREADS_FETCHER = threads
            pullerv2.MAX_THREADS_VALIDATOR = threads
            pullerv2.phase1_fetch_codes(accounts, callback=bot_callback)
            pullerv2.phase2_validate_codes(accounts, codes=None, callback=bot_callback)
            results_folders = glob.glob("validation_results_*")
            if results_folders:
                results_path = max(results_folders, key=os.path.getmtime)

        # Notify completion
        asyncio.run_coroutine_threadsafe(
            application.bot.send_message(chat_id=chat_id, text=f"✅ **Tool `{tool_name.upper()}` has finished!**\nSending results...", parse_mode=ParseMode.MARKDOWN),
            application.loop
        )

        # Zip results if it's a folder
        if results_path and os.path.exists(results_path):
            final_file = results_path
            if os.path.isdir(results_path):
                zip_name = f"{results_path}_{int(time.time())}"
                shutil.make_archive(zip_name, 'zip', results_path)
                final_file = f"{zip_name}.zip"

            # Send the file
            asyncio.run_coroutine_threadsafe(
                application.bot.send_document(
                    chat_id=chat_id,
                    document=open(final_file, 'rb'),
                    caption=f"📦 **Results: {tool_name.upper()}**\n━━━━━━━━━━━━━━━━━━━━\nDone!{get_footer()}",
                    parse_mode=ParseMode.MARKDOWN
                ),
                application.loop
            )
        else:
            bot_callback("✅ Process finished, but no results file was generated.")

    except Exception as e:
        logger.error(f"Error in {tool_name}: {e}", exc_info=True)
        asyncio.run_coroutine_threadsafe(
            application.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg_id,
                text=f"❌ **Crash Error in `{tool_name.upper()}`**\n\n`{str(e)}`",
                parse_mode=ParseMode.MARKDOWN
            ),
            application.loop
        )

# --- Main Entry Point ---

if __name__ == '__main__':
    # Ensure initial admin is authorized
    if not database.is_approved(ADMIN_ID):
        database.set_approved(ADMIN_ID, True)

    # Check for token
    if not BOT_TOKEN or ":" not in BOT_TOKEN:
        print("CRITICAL ERROR: No valid TELEGRAM_BOT_TOKEN provided.")
        exit(1)

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('me', me_command))
    application.add_handler(CommandHandler('threads', threads_command))
    application.add_handler(CommandHandler('proxy', proxy_command))
    application.add_handler(CommandHandler('approve', approve))
    application.add_handler(CommandHandler('add_credits', add_credits))
    application.add_handler(CommandHandler('users', users))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    logger.info("Bot started successfully.")
    application.run_polling()

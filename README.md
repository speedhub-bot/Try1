# 🤖 ToolBot - All-in-One Telegram Bot

A powerful Telegram bot that integrates multiple scraping and checking tools with a credit-based system and administrative controls.

## 🚀 Features
- **5 Integrated Tools**: Flux Scraper, Hotmail Checker, Advanced Hit Checker, Rewards Points Checker, and Code Puller.
- **Credit System**: Each run costs 1 credit. Admin can manage credits.
- **Admin Dashboard**: Approve users, manage credits, and view user lists.
- **Asynchronous Execution**: Tools run in background without blocking the bot.
- **Real-time Status**: Live progress updates in Telegram messages.
- **Auto-Installation**: `start.py` automatically installs missing dependencies.

## 🛠 Setup & Installation

1. **Clone/Download** the repository to your server or PC.
2. **Install Python 3.10+** if you haven't already.
3. **Set your Bot Token**:
   - Rename `.env.example` to `.env` and put your token there.
   - OR set the environment variable: `export TELEGRAM_BOT_TOKEN="your_token_here"`
4. **Run the Bot**:
   ```bash
   python start.py
   ```
   *This will automatically install all required modules and start the bot.*

## 👑 Admin Commands
- `/start` - Main dashboard
- `/approve <user_id>` - Give a user access to the bot
- `/add_credits <user_id> <amount>` - Add credits to a user
- `/users` - List all registered users
- `/help` - Show help menu

## 💎 Credits
**Admin UID:** `5944410248`
Developed with top-notch presentation and stability.

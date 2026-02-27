import sys
import subprocess
import os

def check_and_install():
    # Map of module name to package name
    dependencies = {
        "telegram": "python-telegram-bot[job-queue]>=20.0",
        "requests": "requests",
        "bs4": "beautifulsoup4",
        "rich": "rich",
        "colorama": "colorama",
        "pycountry": "pycountry",
        "curl_cffi": "curl_cffi",
        "user_agent": "user-agent",
        "urllib3": "urllib3"
    }

    missing = []
    for module, package in dependencies.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    if missing:
        print(f"📦 Missing modules found: {len(missing)}")
        print(f"🛠 Installing: {', '.join(missing)}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
            print("✅ Installation successful!\n")
        except Exception as e:
            print(f"❌ Error installing dependencies: {e}")
            print("Please try running: pip install -r requirements.txt")
            sys.exit(1)

if __name__ == "__main__":
    print("🚀 ToolBot Auto-Setup starting...")
    check_and_install()

    print("✨ Starting bot...")
    try:
        # Run bot.py as a module to ensure imports work correctly
        # We use python3 bot.py directly as it is standard
        os.system(f"{sys.executable} bot.py")
    except KeyboardInterrupt:
        print("\n👋 Bot stopped.")
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")

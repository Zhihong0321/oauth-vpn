"""
mitmproxy addon — injects Google session cookies for *.google.com.
"""

import threading
import logging
import cookie_manager
from mitmproxy import http
from mitmproxy.log import log_tier

logger = logging.getLogger("gemshare")

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
            print(f"[GemShare] Startup: {len(cookies)} cookies loaded from file", flush=True)
        else:
            print("[GemShare] Startup: no cookies found — upload via dashboard", flush=True)

    def request(self, flow: http.HTTPFlow):
        host = flow.request.pretty_host
        if not _is_google(host):
            return

        cookies = cookie_manager.get_cookies()
        if not cookies:
            print(f"[GemShare] ❌ INJECT SKIP — no cookies — {host}", flush=True)
            return

        existing = flow.request.headers.get("cookie", "")
        merged = _merge_cookies(existing, cookies)
        flow.request.headers["cookie"] = merged

        # Log injected cookie names so we can verify in Railway logs
        injected_names = list(cookies.keys())
        print(f"[GemShare] ✅ INJECT {host} — {len(injected_names)} cookies: {', '.join(injected_names[:8])}{'...' if len(injected_names) > 8 else ''}", flush=True)


addons = [GeminiCookieInjector()]

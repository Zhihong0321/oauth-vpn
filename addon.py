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
    """Merge browser cookies with our injected session cookies.
    Our cookies ALWAYS win — we override any browser cookie that shares a name."""
    browser_keep: dict = {}
    for chunk in browser_header.split(";"):
        chunk = chunk.strip()
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            k = k.strip()
            # Only keep browser cookies that we don't have a replacement for
            if k not in our_cookies and k not in cookie_manager.SESSION_COOKIE_NAMES:
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

    def response(self, flow: http.HTTPFlow):
        """Strip Set-Cookie headers for session cookies so the browser never
        overwrites our injected cookies with empty/logged-out values."""
        host = flow.request.pretty_host
        if not _is_google(host):
            return

        # Remove Set-Cookie headers that would overwrite our session cookies
        cookies_to_keep = []
        removed = 0
        for header_value in flow.response.headers.get_all("set-cookie"):
            # Parse cookie name from "name=value; ..." format
            name = header_value.split("=", 1)[0].strip()
            if name in cookie_manager.SESSION_COOKIE_NAMES:
                removed += 1
            else:
                cookies_to_keep.append(header_value)

        if removed > 0:
            # Remove all set-cookie headers and re-add only the non-session ones
            del flow.response.headers["set-cookie"]
            for val in cookies_to_keep:
                flow.response.headers.add("set-cookie", val)
            print(f"[GemShare] 🛡️ STRIPPED {removed} Set-Cookie headers from {host}", flush=True)


addons = [GeminiCookieInjector()]

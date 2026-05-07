"""
mitmproxy addon — injects Google session cookies for *.google.com.

Strategy:
  - Our session cookies (SID, __Secure-*, etc.) always override the browser's.
  - Non-session browser cookies (preferences, CSRF tokens) are preserved.
  - Cookies are fetched from cookie_manager on startup and auto-refreshed.
"""

import threading
import logging
import cookie_manager
from mitmproxy import http

logger = logging.getLogger("gemshare.addon")

GOOGLE_TLDS = ("google.com", "gemini.google.com", "accounts.google.com")


def _is_google(host: str) -> bool:
    return any(host == d or host.endswith("." + d) for d in GOOGLE_TLDS)


def _merge_cookies(browser_header: str, our_cookies: dict) -> str:
    """
    Build merged Cookie header:
      our session cookies  +  browser non-session cookies
    Our cookies win for any name collision.
    """
    browser_keep: dict = {}
    for chunk in browser_header.split(";"):
        chunk = chunk.strip()
        if "=" in chunk:
            k, v = chunk.split("=", 1)
            k = k.strip()
            if k not in cookie_manager.SESSION_COOKIE_NAMES:
                browser_keep[k] = v.strip()

    merged = {**browser_keep, **our_cookies}  # ours override
    return "; ".join(f"{k}={v}" for k, v in merged.items())


class GeminiCookieInjector:
    def __init__(self):
        threading.Thread(target=self._startup_load, daemon=True).start()

    def _startup_load(self):
        try:
            cookie_manager.get_cookies(force_refresh=True)
        except Exception as exc:
            logger.error("Startup cookie load failed: %s", exc)

    def request(self, flow: http.HTTPFlow):
        if not _is_google(flow.request.pretty_host):
            return

        cookies = cookie_manager.get_cookies()
        if not cookies:
            logger.warning("No cookies available — request to %s passes through unmodified", flow.request.pretty_host)
            return

        existing = flow.request.headers.get("cookie", "")
        flow.request.headers["cookie"] = _merge_cookies(existing, cookies)


addons = [GeminiCookieInjector()]

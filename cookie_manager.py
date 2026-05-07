"""
Manages Google session cookies for gemini.google.com.

Priority:
  1. Manually uploaded cookies (via admin dashboard) — always wins
  2. Refresh token exchange (auto, background) — fallback
"""

import os
import time
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

OAUTH_CLIENTS = [
    ("407408718192.apps.googleusercontent.com", "AI39si-gFh59Q9c29QiPgx8mKQKPia5qL14"),
    ("764086051850-6qr4p6gpi6hn506pt8ejuq83di341hur.apps.googleusercontent.com", "d-FL95Q19q7MQmFpd7hHD0Ty"),
    ("77185425430.apps.googleusercontent.com", "OTJgUOQcT7lO7GsGZq2G4IlT"),
]

TOKEN_URL = "https://oauth2.googleapis.com/token"
OAUTH_LOGIN_URL = "https://accounts.google.com/accounts/OAuthLogin"

SESSION_COOKIE_NAMES = {
    "SID", "SSID", "HSID", "LSID",
    "APISID", "SAPISID",
    "__Secure-1PSID", "__Secure-3PSID",
    "__Secure-1PAPISID", "__Secure-3PAPISID",
    "__Secure-1PSIDCC", "__Secure-3PSIDCC",
    "__Secure-1PSIDTS", "__Secure-3PSIDTS",
    "__Secure-ENID",
}

_manual_cookies: dict = {}      # set via POST /cookies — takes priority
_cached_cookies: dict = {}      # from refresh token exchange
_last_refresh: float = 0
_last_error: str = ""
_cookie_source: str = "none"    # "manual" | "refresh_token" | "none"
REFRESH_INTERVAL = 50 * 60


# ─── Manual cookie upload ─────────────────────────────────────────────────────

def set_manual_cookies(cookie_list: list) -> int:
    """
    Accept a list of cookie objects (Cookie-Editor JSON export format).
    Returns number of cookies stored.
    """
    global _manual_cookies, _last_error, _cookie_source, _last_refresh

    parsed: dict = {}
    for item in cookie_list:
        name = item.get("name") or item.get("Name") or item.get("key")
        value = item.get("value") or item.get("Value") or ""
        if name:
            parsed[name] = value

    if not parsed:
        raise ValueError("No valid name/value pairs found in cookie data")

    _manual_cookies = parsed
    _last_error = ""
    _cookie_source = "manual"
    _last_refresh = time.time()
    logger.info("Manual cookies loaded — %d cookies", len(parsed))
    return len(parsed)


# ─── Refresh token exchange ───────────────────────────────────────────────────

def get_refresh_token() -> str:
    return os.environ.get("GOOGLE_REFRESH_TOKEN", "")


def _get_access_token(refresh_token: str) -> Optional[str]:
    for client_id, client_secret in OAUTH_CLIENTS:
        try:
            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            }
            if client_secret:
                data["client_secret"] = client_secret
            resp = requests.post(TOKEN_URL, data=data, timeout=10)
            if resp.status_code == 200 and "access_token" in resp.json():
                return resp.json()["access_token"]
        except Exception as exc:
            logger.debug("Client %s… failed: %s", client_id[:30], exc)
    return None


def _fetch_via_refresh_token() -> dict:
    rt = get_refresh_token()
    if not rt:
        raise ValueError("GOOGLE_REFRESH_TOKEN env var is not set")
    access_token = _get_access_token(rt)
    if not access_token:
        raise RuntimeError("All OAuth2 clients failed to exchange the refresh token")
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    session.get(
        OAUTH_LOGIN_URL,
        params={"source": "ChromiumBrowser", "isAccessToken": "true",
                "sign_in": "1", "access_token": access_token},
        allow_redirects=True, timeout=15,
    )
    cookies = {c.name: c.value for c in session.cookies}
    if not cookies:
        raise RuntimeError("OAuthLogin returned zero cookies")
    return cookies


# ─── Public API ───────────────────────────────────────────────────────────────

def get_cookies(force_refresh: bool = False) -> dict:
    global _cached_cookies, _last_refresh, _last_error, _cookie_source

    # Manual cookies always take priority
    if _manual_cookies:
        return _manual_cookies

    # Auto-refresh from refresh token
    if force_refresh or not _cached_cookies or time.time() - _last_refresh > REFRESH_INTERVAL:
        try:
            _cached_cookies = _fetch_via_refresh_token()
            _last_refresh = time.time()
            _last_error = ""
            _cookie_source = "refresh_token"
        except Exception as exc:
            _last_error = str(exc)
            logger.error("Cookie refresh failed: %s", exc)

    return _cached_cookies


def get_status() -> dict:
    active = _manual_cookies or _cached_cookies
    return {
        "ok": bool(active),
        "cookie_count": len(active),
        "source": _cookie_source,
        "last_refresh_epoch": _last_refresh,
        "age_seconds": int(time.time() - _last_refresh) if _last_refresh else None,
        "refresh_token_set": bool(get_refresh_token()),
        "last_error": _last_error,
    }

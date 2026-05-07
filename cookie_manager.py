"""
Manages Google session cookies for gemini.google.com.

Cookies are persisted to COOKIE_FILE so the admin HTTP process and the
mitmproxy process (separate OS processes) both read from the same source.
"""

import json
import os
import time
import logging
import requests
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

COOKIE_FILE = Path("/tmp/gemshare_cookies.json")

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
    "__Secure-1PSIDRTS", "__Secure-3PSIDRTS",
    "__Secure-ENID", "__Secure-BUCKET",
    "AEC", "SIDCC",
}

_last_error: str = ""


# ─── File-based shared storage (cross-process) ────────────────────────────────

def _load_from_file() -> dict:
    try:
        if COOKIE_FILE.exists():
            data = json.loads(COOKIE_FILE.read_text())
            return data.get("cookies", {})
    except Exception as exc:
        logger.warning("Cookie file read failed: %s", exc)
    return {}


def _save_to_file(cookies: dict, source: str):
    try:
        COOKIE_FILE.write_text(json.dumps({
            "cookies": cookies,
            "source": source,
            "saved_at": time.time(),
        }))
    except Exception as exc:
        logger.warning("Cookie file write failed: %s", exc)


def _file_meta() -> dict:
    try:
        if COOKIE_FILE.exists():
            return json.loads(COOKIE_FILE.read_text())
    except Exception:
        pass
    return {}


# ─── Manual cookie upload ─────────────────────────────────────────────────────

def set_manual_cookies(cookie_list: list) -> int:
    global _last_error
    parsed: dict = {}
    for item in cookie_list:
        name = item.get("name") or item.get("Name") or item.get("key")
        value = item.get("value") or item.get("Value") or ""
        if name:
            parsed[name] = value

    if not parsed:
        raise ValueError("No valid name/value pairs found in cookie data")

    _save_to_file(parsed, "manual")
    _last_error = ""
    logger.info("Manual cookies saved — %d cookies", len(parsed))
    return len(parsed)


# ─── Refresh token fallback ───────────────────────────────────────────────────

def get_refresh_token() -> str:
    return os.environ.get("GOOGLE_REFRESH_TOKEN", "")


def _get_access_token(refresh_token: str) -> Optional[str]:
    for client_id, client_secret in OAUTH_CLIENTS:
        try:
            data = {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id}
            if client_secret:
                data["client_secret"] = client_secret
            resp = requests.post(TOKEN_URL, data=data, timeout=10)
            if resp.status_code == 200 and "access_token" in resp.json():
                return resp.json()["access_token"]
        except Exception as exc:
            logger.debug("Client failed: %s", exc)
    return None


def _fetch_via_refresh_token() -> dict:
    rt = get_refresh_token()
    if not rt:
        raise ValueError("GOOGLE_REFRESH_TOKEN not set")
    access_token = _get_access_token(rt)
    if not access_token:
        raise RuntimeError("All OAuth2 clients failed")
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    session.get(OAUTH_LOGIN_URL,
                params={"source": "ChromiumBrowser", "isAccessToken": "true",
                        "sign_in": "1", "access_token": access_token},
                allow_redirects=True, timeout=15)
    cookies = {c.name: c.value for c in session.cookies}
    if not cookies:
        raise RuntimeError("OAuthLogin returned zero cookies")
    return cookies


# ─── Public API ───────────────────────────────────────────────────────────────

def get_cookies(force_refresh: bool = False) -> dict:
    global _last_error

    # Always read from shared file — works across processes
    cookies = _load_from_file()
    if cookies:
        return cookies

    # Fallback: refresh token
    try:
        cookies = _fetch_via_refresh_token()
        _save_to_file(cookies, "refresh_token")
        _last_error = ""
        return cookies
    except Exception as exc:
        _last_error = str(exc)
        logger.error("Cookie fetch failed: %s", exc)
        return {}


def get_status() -> dict:
    meta = _file_meta()
    cookies = meta.get("cookies", {})
    saved_at = meta.get("saved_at")
    return {
        "ok": bool(cookies),
        "cookie_count": len(cookies),
        "source": meta.get("source", "none"),
        "last_refresh_epoch": saved_at,
        "age_seconds": int(time.time() - saved_at) if saved_at else None,
        "refresh_token_set": bool(get_refresh_token()),
        "last_error": _last_error,
    }

"""
Converts a Google OAuth2 refresh token into web session cookies
for gemini.google.com by cycling through known public OAuth2 clients.
"""

import os
import time
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

# Known public / installed-app Google OAuth2 clients (no secrets required for some).
# We try each in order until one successfully exchanges the refresh token.
OAUTH_CLIENTS = [
    # Google OAuth2 Playground
    ("407408718192.apps.googleusercontent.com", "AI39si-gFh59Q9c29QiPgx8mKQKPia5qL14"),
    # gcloud / Google Cloud SDK
    ("764086051850-6qr4p6gpi6hn506pt8ejuq83di341hur.apps.googleusercontent.com", "d-FL95Q19q7MQmFpd7hHD0Ty"),
    # Chrome browser (embedded, publicly known)
    ("77185425430.apps.googleusercontent.com", "OTJgUOQcT7lO7GsGZq2G4IlT"),
]

TOKEN_URL = "https://oauth2.googleapis.com/token"
OAUTH_LOGIN_URL = "https://accounts.google.com/accounts/OAuthLogin"

# Google session cookie names — these are the ones we inject.
# Anything NOT in this set coming from the browser is left untouched.
SESSION_COOKIE_NAMES = {
    "SID", "SSID", "HSID", "LSID",
    "APISID", "SAPISID",
    "__Secure-1PSID", "__Secure-3PSID",
    "__Secure-1PAPISID", "__Secure-3PAPISID",
    "__Secure-1PSIDCC", "__Secure-3PSIDCC",
    "__Secure-1PSIDTS", "__Secure-3PSIDTS",
    "__Secure-ENID",
}

_cached_cookies: dict = {}
_last_refresh: float = 0
_last_error: str = ""
REFRESH_INTERVAL = 50 * 60  # refresh 10 min before 1-hour expiry


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
                logger.info("Access token obtained via client %s…", client_id[:30])
                return resp.json()["access_token"]
        except Exception as exc:
            logger.debug("Client %s… failed: %s", client_id[:30], exc)

    return None


def _get_cookies_via_oauth_login(access_token: str) -> dict:
    session = requests.Session()
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    session.get(
        OAUTH_LOGIN_URL,
        params={
            "source": "ChromiumBrowser",
            "isAccessToken": "true",
            "sign_in": "1",
            "access_token": access_token,
        },
        allow_redirects=True,
        timeout=15,
    )
    return {c.name: c.value for c in session.cookies}


def fetch_fresh_cookies() -> dict:
    """Exchange refresh token → access token → session cookies. Raises on failure."""
    global _last_error

    rt = get_refresh_token()
    if not rt:
        raise ValueError("GOOGLE_REFRESH_TOKEN env var is not set")

    access_token = _get_access_token(rt)
    if not access_token:
        raise RuntimeError(
            "All OAuth2 clients failed to exchange the refresh token. "
            "The token may be expired or from an unrecognised client."
        )

    cookies = _get_cookies_via_oauth_login(access_token)
    if not cookies:
        raise RuntimeError("OAuthLogin succeeded but returned zero cookies")

    return cookies


def get_cookies(force_refresh: bool = False) -> dict:
    """Return cached cookies, refreshing if stale or forced."""
    global _cached_cookies, _last_refresh, _last_error

    if force_refresh or not _cached_cookies or time.time() - _last_refresh > REFRESH_INTERVAL:
        try:
            _cached_cookies = fetch_fresh_cookies()
            _last_refresh = time.time()
            _last_error = ""
            logger.info("Cookies refreshed — %d cookies active", len(_cached_cookies))
        except Exception as exc:
            _last_error = str(exc)
            logger.error("Cookie refresh failed: %s", exc)

    return _cached_cookies


def get_status() -> dict:
    return {
        "ok": bool(_cached_cookies) and not _last_error,
        "cookie_count": len(_cached_cookies),
        "last_refresh_epoch": _last_refresh,
        "age_seconds": int(time.time() - _last_refresh) if _last_refresh else None,
        "refresh_token_set": bool(get_refresh_token()),
        "last_error": _last_error,
    }

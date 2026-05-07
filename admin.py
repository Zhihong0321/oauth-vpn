"""
Lightweight admin HTTP server (FastAPI).
Railway exposes this as the public HTTPS URL.

Routes:
  GET /           → Status dashboard (HTML)
  GET /cert       → Download mitmproxy CA certificate (.pem)
  GET /refresh    → Force cookie refresh
  GET /status     → JSON health check
"""

import os
import time
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, Response

import cookie_manager

app = FastAPI(title="GemShare Admin", docs_url=None, redoc_url=None)

CERT_PATHS = [
    Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem",
    Path("/root/.mitmproxy/mitmproxy-ca-cert.pem"),
]


def _find_cert() -> Optional[Path]:
    for p in CERT_PATHS:
        if p.exists():
            return p
    return None


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard():
    s = cookie_manager.get_status()
    ok = s["ok"]
    age = s["age_seconds"]
    age_str = f"{age}s ago" if age is not None else "never"
    color = "2ecc71" if ok else "e74c3c"
    badge = "✅ Cookies active" if ok else "❌ No cookies"
    error_block = f'<p style="color:#e74c3c">Error: {s["last_error"]}</p>' if s["last_error"] else ""
    cert_exists = _find_cert() is not None

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>GemShare</title>
<style>
  body {{font-family:monospace;max-width:680px;margin:48px auto;padding:24px;background:#0f0f0f;color:#eee}}
  h1 {{color:#1a73e8}} h2{{color:#aaa;font-size:.9em;font-weight:normal;margin-top:2em}}
  .badge {{display:inline-block;padding:4px 12px;border-radius:12px;background:#{color};color:#fff;font-weight:bold}}
  .btn {{display:inline-block;padding:10px 20px;background:#1a73e8;color:white;text-decoration:none;
         border-radius:4px;margin:4px 4px 4px 0;font-family:monospace}}
  .btn.sec {{background:#333}}
  code {{background:#1e1e1e;padding:2px 6px;border-radius:3px}}
  table {{border-collapse:collapse;width:100%}}
  td,th {{padding:6px 12px;border:1px solid #333;text-align:left}}
  th {{background:#1e1e1e}}
</style></head>
<body>
<h1>GemShare Proxy</h1>
<span class="badge">{badge}</span>
{error_block}

<h2>COOKIE STATUS</h2>
<table>
<tr><th>Field</th><th>Value</th></tr>
<tr><td>Cookie count</td><td>{s['cookie_count']}</td></tr>
<tr><td>Last refreshed</td><td>{age_str}</td></tr>
<tr><td>Refresh token set</td><td>{'Yes' if s['refresh_token_set'] else 'No — set GOOGLE_REFRESH_TOKEN env var'}</td></tr>
</table>

<h2>ACTIONS</h2>
<a class="btn" href="/cert">⬇ Download CA Certificate {'✅' if cert_exists else '(generating…)'}</a>
<a class="btn sec" href="/refresh">🔄 Force Cookie Refresh</a>
<a class="btn sec" href="/status">📋 JSON Status</a>

<h2>WINDOWS 11 SETUP</h2>
<ol>
<li>Click <b>Download CA Certificate</b> above → save the <code>.pem</code> file</li>
<li>Rename it to <code>gemshare-ca.crt</code> → double-click → <em>Install Certificate</em></li>
<li>Choose <em>Local Machine</em> → <em>Place all certificates in the following store</em> → <em>Trusted Root Certification Authorities</em></li>
<li>Open <em>Settings → Network &amp; Internet → Proxy → Manual proxy setup</em></li>
<li>Enable → set <b>Address</b> to your Railway TCP proxy hostname, <b>Port</b> 8080</li>
<li>Open <a href="https://gemini.google.com" style="color:#1a73e8">gemini.google.com</a> — you should be auto-logged in</li>
</ol>

</body></html>"""


@app.get("/cert")
def download_cert():
    cert_path = _find_cert()
    if cert_path is None:
        return Response(
            "CA certificate not yet generated. mitmproxy needs ~5s after startup. Retry shortly.",
            status_code=503,
            media_type="text/plain",
        )
    data = cert_path.read_bytes()
    return Response(
        content=data,
        media_type="application/x-pem-file",
        headers={"Content-Disposition": 'attachment; filename="gemshare-ca.pem"'},
    )


@app.get("/refresh")
def force_refresh():
    try:
        cookie_manager.get_cookies(force_refresh=True)
        s = cookie_manager.get_status()
        return HTMLResponse(
            f"<p style='color:green'>✅ Refreshed — {s['cookie_count']} cookies active. "
            "<a href='/'>Back</a></p>"
        )
    except Exception as exc:
        return HTMLResponse(
            f"<p style='color:red'>❌ Refresh failed: {exc}. <a href='/'>Back</a></p>",
            status_code=500,
        )


@app.get("/status")
def status():
    return JSONResponse(cookie_manager.get_status())


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

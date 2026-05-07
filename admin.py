"""
Admin HTTP server — Railway public HTTPS URL.

GET  /          dashboard
GET  /cert      download mitmproxy CA cert
GET  /refresh   force refresh token exchange
POST /cookies   upload cookie JSON (Cookie-Editor export)
GET  /status    JSON health
"""

import json
import os
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, Request
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


# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard():
    s = cookie_manager.get_status()
    ok = s["ok"]
    age = s["age_seconds"]
    age_str = f"{age}s ago" if age is not None else "never"
    color = "2ecc71" if ok else "e74c3c"
    badge = "✅ Cookies active" if ok else "❌ No cookies"
    source_str = {"manual": "manual upload", "refresh_token": "refresh token", "none": "—"}.get(s["source"], s["source"])
    error_block = f'<p style="color:#e74c3c;margin:8px 0">⚠ {s["last_error"]}</p>' if s["last_error"] else ""
    cert_ok = _find_cert() is not None

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>GemShare</title>
<style>
body{{font-family:monospace;max-width:700px;margin:48px auto;padding:24px;background:#0f0f0f;color:#eee}}
h1{{color:#1a73e8;margin-bottom:4px}}
h2{{color:#888;font-size:.8em;font-weight:normal;text-transform:uppercase;letter-spacing:.1em;margin:2em 0 .5em}}
.badge{{display:inline-block;padding:4px 14px;border-radius:12px;background:#{color};color:#fff;font-weight:bold;font-size:.9em}}
.btn{{display:inline-block;padding:9px 18px;background:#1a73e8;color:white;text-decoration:none;border-radius:4px;margin:3px 3px 3px 0;font-family:monospace;font-size:.9em}}
.btn.grey{{background:#2a2a2a;border:1px solid #444}}
code{{background:#1e1e1e;padding:2px 6px;border-radius:3px;font-size:.85em}}
table{{border-collapse:collapse;width:100%;margin-bottom:1em}}
td,th{{padding:6px 12px;border:1px solid #2a2a2a;text-align:left;font-size:.9em}}
th{{background:#1a1a1a;color:#aaa}}
textarea{{width:100%;height:120px;background:#1a1a1a;color:#eee;border:1px solid #444;border-radius:4px;padding:8px;font-family:monospace;font-size:.8em;box-sizing:border-box}}
.step{{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px;padding:16px;margin-bottom:12px}}
.step b{{color:#1a73e8}}
</style></head>
<body>
<h1>GemShare Proxy</h1>
<span class="badge">{badge}</span>

<h2>Cookie Status</h2>
<table>
<tr><th>Field</th><th>Value</th></tr>
<tr><td>Cookie count</td><td>{s['cookie_count']}</td></tr>
<tr><td>Source</td><td>{source_str}</td></tr>
<tr><td>Last loaded</td><td>{age_str}</td></tr>
<tr><td>Refresh token set</td><td>{'Yes' if s['refresh_token_set'] else 'No'}</td></tr>
</table>
{error_block}

<h2>Upload Cookies (Manual — use this)</h2>
<div class="step">
<b>Step 1</b> — Install <a href="https://chrome.google.com/webstore/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm" style="color:#1a73e8" target="_blank">Cookie-Editor</a> extension in Chrome<br><br>
<b>Step 2</b> — Log into <code>leanhhu061212@gmail.com</code>, go to <code>gemini.google.com</code><br><br>
<b>Step 3</b> — Click Cookie-Editor icon → <b>Export → Export as JSON</b> (copies to clipboard)<br><br>
<b>Step 4</b> — Paste below and click Upload
</div>
<form method="POST" action="/cookies">
<textarea name="cookies" placeholder='Paste Cookie-Editor JSON here...'></textarea><br>
<button type="submit" style="margin-top:8px;padding:9px 18px;background:#1a73e8;color:white;border:none;border-radius:4px;font-family:monospace;cursor:pointer">⬆ Upload Cookies</button>
</form>

<h2>Actions</h2>
<a class="btn" href="/cert">⬇ CA Certificate {'✅' if cert_ok else '(wait…)'}</a>
<a class="btn grey" href="/refresh">🔄 Try Refresh Token</a>
<a class="btn grey" href="/status">📋 JSON Status</a>

<h2>Windows 11 Proxy Setup</h2>
<ol style="line-height:2">
<li>Download CA cert above → rename to <code>.crt</code> → double-click → Install → <b>Local Machine</b> → <b>Trusted Root Certification Authorities</b></li>
<li>Settings → Network &amp; Internet → Proxy → Manual proxy setup → <b>On</b></li>
<li>Address = your Railway TCP proxy host &nbsp;|&nbsp; Port = <b>8080</b></li>
<li>Open <code>gemini.google.com</code> → auto-logged in ✅</li>
</ol>
</body></html>"""


# ─── Cookie upload ────────────────────────────────────────────────────────────

@app.post("/cookies", response_class=HTMLResponse)
async def upload_cookies(request: Request):
    form = await request.form()
    raw = form.get("cookies", "").strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = list(data.values()) if not any("name" in v for v in data.values() if isinstance(v, dict)) else [{"name": k, "value": v} for k, v in data.items()]
        count = cookie_manager.set_manual_cookies(data)
        return HTMLResponse(f'<p style="color:#2ecc71;font-family:monospace">✅ {count} cookies loaded. <a href="/">Back to dashboard</a></p>')
    except Exception as exc:
        return HTMLResponse(f'<p style="color:#e74c3c;font-family:monospace">❌ Error: {exc} <a href="/">Back</a></p>', status_code=400)


# ─── Other routes ─────────────────────────────────────────────────────────────

@app.get("/cert")
def download_cert():
    cert_path = _find_cert()
    if cert_path is None:
        return Response("Cert not ready — retry in 10s", status_code=503, media_type="text/plain")
    return Response(
        content=cert_path.read_bytes(),
        media_type="application/x-pem-file",
        headers={"Content-Disposition": 'attachment; filename="gemshare-ca.pem"'},
    )


@app.get("/refresh")
def force_refresh():
    try:
        cookie_manager.get_cookies(force_refresh=True)
        s = cookie_manager.get_status()
        return HTMLResponse(f'<p style="font-family:monospace">✅ {s["cookie_count"]} cookies active. <a href="/">Back</a></p>')
    except Exception as exc:
        return HTMLResponse(f'<p style="color:#e74c3c;font-family:monospace">❌ {exc} <a href="/">Back</a></p>', status_code=500)


@app.get("/status")
def status():
    return JSONResponse(cookie_manager.get_status())


# ─── Entry ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = 8080  # Railway HTTP domain routes to this port
    print(f"[GemShare] Admin server starting on port {port}", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

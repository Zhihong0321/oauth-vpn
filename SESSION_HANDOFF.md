# GemShare Session Handoff

## What This Project Does
Shares a Google Gemini account across a team via a proxy server. Users connect through a Railway-hosted mitmproxy that injects valid Google session cookies into every request, making Gemini think you are logged in.

---

## Current State ✅ WORKING

### What Works (confirmed end-to-end)
- Railway Hub deployed at `https://oauth-vpn-production.up.railway.app`
- mitmproxy running on `tramway.proxy.rlwy.net:25307`
- Cookie injection confirmed working (Railway logs show INJECT ✅)
- Windows proxy + cert install working correctly
- Edge/Chrome InPrivate → `gemini.google.com/app` → auto-logged in as leanhhu061212@gmail.com ✅
- Tauri app shows honest 4-item status checklist (cert, proxy, cookies, Google login from machine)

### What Still Needs Doing
- Rebuild Tauri `.exe` via GitHub Actions (push tag `v0.1.1`)
- Add GitHub secrets for signing if not already done

---

## The Bug That Wasted 4 Days

**`enable_proxy()` wrote to the wrong registry key.**

The Rust code was writing:
```
HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings\ProxyEnable = 1
HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings\ProxyServer = tramway...
```

Windows 10/11 Settings UI and Chrome/Edge read from a **different binary blob**:
```
HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings\Connections\DefaultConnectionSettings
```

The old key is legacy WinInet (PowerShell Invoke-WebRequest reads it). Chrome/Edge read `DefaultConnectionSettings`. Since the blob was never updated, Windows showed "Proxy: Off", Chrome/Edge used no proxy, and cookies were never injected into browser traffic.

**Fix:** `enable_proxy()` now builds and writes the correct `DefaultConnectionSettings` binary blob (flags=0x05 = auto-detect off + manual proxy on), plus `SavedLegacySettings`. Pushed in commit `0e46d71`.

---

## Architecture

```
User (Windows)
  → System Proxy (set by Tauri app via DefaultConnectionSettings blob)
  → tramway.proxy.rlwy.net:25307  (Railway TCP proxy)
  → mitmproxy container port 8888  (injects cookies)
  → gemini.google.com/app

Admin (Tauri app)
  → Stores Google account cookies locally
  → On Connect: pushes cookies to Hub via POST /api/sync
  → Hub writes to /tmp/gemshare_cookies.json
  → mitmproxy reads from same file and injects
```

---

## Railway Hub Endpoints
| Endpoint | Purpose |
|---|---|
| `GET /` | Admin dashboard |
| `GET /status` | Cookie status JSON |
| `GET /log` | Live injection log — CHECK THIS FIRST when debugging |
| `GET /cert` | Download mitmproxy CA certificate |
| `GET /api/myip` | Railway's outbound IP |
| `POST /api/sync` | Push cookies from Tauri to Hub |
| `GET /api/check-session` | Verify cookies with Google (through mitmproxy on Railway) |

---

## Key Files
| File | Purpose |
|---|---|
| `admin.py` | FastAPI server (Railway) |
| `cookie_manager.py` | Cookie storage/retrieval (file-based: `/tmp/gemshare_cookies.json`) |
| `addon.py` | mitmproxy addon — injects cookies for *.google.com |
| `start.sh` | Starts admin (port 8080) + mitmproxy (port 8888) |
| `Dockerfile` | mitmproxy installed and cert generated BEFORE other deps |
| `tauri-app/` | Desktop app (Rust + HTML/JS) |

---

## Tauri App Status Panel
The app now shows 4 honest real-time checks:
1. **CA Certificate** — checks Windows CurrentUser Root cert store for mitmproxy cert
2. **System Proxy** — checks registry ProxyEnable + ProxyServer
3. **Hub Cookies** — fetches /status from Railway
4. **Google Login (from your machine)** — runs PowerShell Invoke-WebRequest through the proxy to myaccount.google.com, checks if response stays on myaccount.google.com (= logged in) or redirects to signin (= rejected)

**Connect Everything** button: installs cert → enables proxy → rechecks all 4.

---

## How to Build Release .exe
```powershell
cd "G:\Gemini OAUTH VPN\tauri-app"
$env:TAURI_SIGNING_PRIVATE_KEY = (Get-Content "..\gemshare.key" -Raw)
npm run build
# Installer at: src-tauri\target\release\bundle\nsis\GemShare_0.1.1_x64-setup.exe
```

Or via GitHub Actions (push a tag):
```powershell
cd "C:\Users\Eternalgy\AppData\Local\Temp\gemshare-temp"
git tag v0.1.1
git push origin v0.1.1
```

---

## How to Push Code
```powershell
cd "C:\Users\Eternalgy\AppData\Local\Temp\gemshare-temp"
git pull
# copy changed files here, then:
git add <files>
git commit -m "message"
git push
```
Do NOT push from `G:\Gemini OAUTH VPN` — git objects are bloated from a previous node_modules incident.

---

## Important IPs
| IP | What it is |
|---|---|
| `tramway.proxy.rlwy.net:25307` | TCP proxy address (stable) |

**Note:** Railway's outbound IP can change on redeploy. If cookies stop working after a Railway redeploy, check `/api/myip` and re-create cookies from that IP.

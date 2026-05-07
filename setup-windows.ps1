# GemShare Windows Setup Script
# Run as Administrator in PowerShell
# Usage: .\setup-windows.ps1

$ADMIN_URL  = "https://oauth-vpn-production.up.railway.app"
$PROXY_HOST = "tramway.proxy.rlwy.net"
$PROXY_PORT = "25307"
$regPath    = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"

Write-Host ""
Write-Host "=== GemShare Proxy Setup ===" -ForegroundColor Cyan

# ── 1. Turn off proxy so download doesn't go through mitmproxy ───────────────
Write-Host "`n[1/3] Disabling proxy temporarily for cert download..." -ForegroundColor Yellow
Set-ItemProperty -Path $regPath -Name ProxyEnable -Value 0

# ── 2. Download and install CA certificate ───────────────────────────────────
Write-Host "`n[2/3] Downloading and installing CA certificate..." -ForegroundColor Yellow
try {
    $bytes = (Invoke-WebRequest -Uri "$ADMIN_URL/cert" -UseBasicParsing -NoProxy).Content
    $cert  = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2(,$bytes)
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store("Root","LocalMachine")
    $store.Open("ReadWrite")
    $store.Add($cert)
    $store.Close()
    Write-Host "      Certificate installed in Trusted Root Certification Authorities" -ForegroundColor Green
} catch {
    Write-Host "      FAILED: $_" -ForegroundColor Red
    Write-Host "      Make sure you are running as Administrator and Railway is online."
    exit 1
}

# ── 3. Enable proxy ───────────────────────────────────────────────────────────
Write-Host "`n[3/3] Enabling proxy ${PROXY_HOST}:${PROXY_PORT}..." -ForegroundColor Yellow
Set-ItemProperty -Path $regPath -Name ProxyEnable   -Value 1
Set-ItemProperty -Path $regPath -Name ProxyServer   -Value "${PROXY_HOST}:${PROXY_PORT}"
Set-ItemProperty -Path $regPath -Name ProxyOverride -Value "localhost;127.0.0.1;<local>"

$sig  = '[DllImport("wininet.dll")] public static extern bool InternetSetOption(IntPtr h,int o,IntPtr b,int l);'
$type = Add-Type -MemberDefinition $sig -Name WinINet -Namespace Win32 -PassThru
$type::InternetSetOption([IntPtr]::Zero,39,[IntPtr]::Zero,0) | Out-Null
$type::InternetSetOption([IntPtr]::Zero,37,[IntPtr]::Zero,0) | Out-Null
Write-Host "      Proxy enabled" -ForegroundColor Green

Write-Host ""
Write-Host "=== Done! Close Chrome fully, reopen, go to gemini.google.com ===" -ForegroundColor Cyan

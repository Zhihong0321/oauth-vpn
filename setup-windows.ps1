# GemShare Windows Setup Script
# Run as Administrator in PowerShell
# Usage: .\setup-windows.ps1

$ADMIN_URL   = "https://oauth-vpn-production.up.railway.app"
$PROXY_HOST  = "tramway.proxy.rlwy.net"
$PROXY_PORT  = "25307"
$CERT_FILE   = "$env:TEMP\gemshare-ca.crt"

Write-Host ""
Write-Host "=== GemShare Proxy Setup ===" -ForegroundColor Cyan

# ── 1. Download CA certificate ────────────────────────────────────────────────
Write-Host "`n[1/3] Downloading CA certificate..." -ForegroundColor Yellow
try {
    Invoke-WebRequest -Uri "$ADMIN_URL/cert" -OutFile $CERT_FILE -UseBasicParsing
    Write-Host "      Saved to $CERT_FILE" -ForegroundColor Green
} catch {
    Write-Host "      FAILED: $_" -ForegroundColor Red
    Write-Host "      Make sure the Railway service is online and try again."
    exit 1
}

# ── 2. Install CA certificate into Trusted Root store ────────────────────────
Write-Host "`n[2/3] Installing CA certificate..." -ForegroundColor Yellow
try {
    $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($CERT_FILE)
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store(
        "Root", "LocalMachine"
    )
    $store.Open("ReadWrite")
    $store.Add($cert)
    $store.Close()
    Write-Host "      Installed in Trusted Root Certification Authorities" -ForegroundColor Green
} catch {
    Write-Host "      FAILED: $_" -ForegroundColor Red
    Write-Host "      Make sure you are running this script as Administrator."
    exit 1
}

# ── 3. Set Windows system proxy ───────────────────────────────────────────────
Write-Host "`n[3/3] Configuring Windows proxy..." -ForegroundColor Yellow
$regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
Set-ItemProperty -Path $regPath -Name ProxyEnable  -Value 1
Set-ItemProperty -Path $regPath -Name ProxyServer  -Value "${PROXY_HOST}:${PROXY_PORT}"
Set-ItemProperty -Path $regPath -Name ProxyOverride -Value "localhost;127.0.0.1;<local>"
Write-Host "      Proxy set to ${PROXY_HOST}:${PROXY_PORT}" -ForegroundColor Green

# Notify WinINet so browsers pick up the change immediately
$signature = @'
[DllImport("wininet.dll", SetLastError=true)]
public static extern bool InternetSetOption(IntPtr hInternet, int dwOption, IntPtr lpBuffer, int dwBufferLength);
'@
$type = Add-Type -MemberDefinition $signature -Name "WinINet" -Namespace "Win32" -PassThru
$type::InternetSetOption([IntPtr]::Zero, 39, [IntPtr]::Zero, 0) | Out-Null
$type::InternetSetOption([IntPtr]::Zero, 37, [IntPtr]::Zero, 0) | Out-Null

Write-Host ""
Write-Host "=== Setup complete! ===" -ForegroundColor Cyan
Write-Host "Open gemini.google.com in any browser — you should be auto-logged in." -ForegroundColor White
Write-Host ""
Write-Host "To disable proxy later, run: .\setup-windows.ps1 -Disable" -ForegroundColor DarkGray

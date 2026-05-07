@echo off
title GemShare — Disable Proxy

net session >nul 2>&1
if %errorLevel% neq 0 (
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

powershell -ExecutionPolicy Bypass -Command ^
    "$reg = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings';" ^
    "Set-ItemProperty $reg ProxyEnable 0;" ^
    "$t = Add-Type -MemberDefinition '[DllImport(""wininet.dll"")] public static extern bool InternetSetOption(IntPtr h,int o,IntPtr b,int l);' -Name W -Namespace N -PassThru;" ^
    "$t::InternetSetOption(0,39,0,0)|Out-Null; $t::InternetSetOption(0,37,0,0)|Out-Null;" ^
    "Write-Host 'Proxy disabled. Back to normal browsing.' -ForegroundColor Green;"

pause

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use tauri::Manager;

// ── Data types ────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Account {
    pub id: String,
    pub label: String,
    pub email: String,
    pub cookies: Vec<serde_json::Value>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct AppData {
    pub accounts: Vec<Account>,
    pub active_account_id: Option<String>,
    pub hub_url: String,
}

impl Default for AppData {
    fn default() -> Self {
        AppData {
            accounts: vec![],
            active_account_id: None,
            hub_url: "https://oauth-vpn-production.up.railway.app".into(),
        }
    }
}

// ── Storage ───────────────────────────────────────────────────────────────────

fn data_path(app: &tauri::AppHandle) -> PathBuf {
    app.path().app_data_dir().unwrap().join("accounts.json")
}

fn load(app: &tauri::AppHandle) -> AppData {
    let p = data_path(app);
    if p.exists() {
        if let Ok(s) = fs::read_to_string(&p) {
            if let Ok(d) = serde_json::from_str(&s) {
                return d;
            }
        }
    }
    AppData::default()
}

fn save(app: &tauri::AppHandle, data: &AppData) {
    let p = data_path(app);
    fs::create_dir_all(p.parent().unwrap()).ok();
    fs::write(p, serde_json::to_string_pretty(data).unwrap()).ok();
}

// ── Commands ──────────────────────────────────────────────────────────────────

#[tauri::command]
fn get_accounts(app: tauri::AppHandle) -> AppData {
    load(&app)
}

#[tauri::command]
fn add_account(app: tauri::AppHandle, label: String, email: String) -> String {
    let mut data = load(&app);
    let id = uuid::Uuid::new_v4().to_string();
    data.accounts.push(Account { id: id.clone(), label, email, cookies: vec![] });
    save(&app, &data);
    id
}

#[tauri::command]
fn update_cookies(
    app: tauri::AppHandle,
    account_id: String,
    cookies: Vec<serde_json::Value>,
) -> Result<(), String> {
    let mut data = load(&app);
    let acct = data.accounts.iter_mut()
        .find(|a| a.id == account_id)
        .ok_or("Account not found")?;
    acct.cookies = cookies;

    // If this is the active account, sync to Hub immediately
    let is_active = data.active_account_id.as_deref() == Some(&account_id);
    let cookies_clone = acct.cookies.clone();
    let hub = data.hub_url.clone();
    save(&app, &data);

    if is_active {
        sync_cookies_to_hub(&hub, &cookies_clone)?;
    }
    Ok(())
}

#[tauri::command]
fn set_active_account(app: tauri::AppHandle, account_id: String) -> Result<(), String> {
    let mut data = load(&app);
    let acct = data.accounts.iter()
        .find(|a| a.id == account_id)
        .ok_or("Account not found")?
        .clone();
    data.active_account_id = Some(account_id);
    sync_cookies_to_hub(&data.hub_url, &acct.cookies)?;
    save(&app, &data);
    Ok(())
}

#[tauri::command]
fn delete_account(app: tauri::AppHandle, account_id: String) {
    let mut data = load(&app);
    data.accounts.retain(|a| a.id != account_id);
    if data.active_account_id.as_deref() == Some(&account_id) {
        data.active_account_id = None;
    }
    save(&app, &data);
}

// ── Hub sync ──────────────────────────────────────────────────────────────────

fn sync_cookies_to_hub(hub_url: &str, cookies: &[serde_json::Value]) -> Result<(), String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(10))
        .no_proxy()
        .build()
        .map_err(|e| e.to_string())?;

    client
        .post(format!("{}/api/sync", hub_url))
        .json(&serde_json::json!({ "cookies": cookies }))
        .send()
        .map_err(|e| format!("Hub sync failed: {}", e))?;
    Ok(())
}

// ── Proxy management ──────────────────────────────────────────────────────────

const PROXY_HOST: &str = "tramway.proxy.rlwy.net";
const PROXY_PORT: &str = "25307";
const REG_PATH: &str = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings";

#[tauri::command]
fn get_cert_status() -> bool {
    let script = r#"
$store = New-Object System.Security.Cryptography.X509Certificates.X509Store('Root','CurrentUser')
$store.Open('ReadOnly')
$found = $store.Certificates | Where-Object { $_.Subject -match 'mitmproxy' }
$store.Close()
if ($found) { Write-Host 'CERT_FOUND' } else { Write-Host 'CERT_MISSING' }
"#;
    let out = std::process::Command::new("powershell")
        .args(["-ExecutionPolicy", "Bypass", "-Command", script])
        .output();
    match out {
        Ok(o) => String::from_utf8_lossy(&o.stdout).contains("CERT_FOUND"),
        Err(_) => false,
    }
}

#[tauri::command]
fn get_proxy_status() -> bool {
    use winreg::{enums::HKEY_CURRENT_USER, RegKey};
    let hkcu = RegKey::predef(HKEY_CURRENT_USER);
    if let Ok(k) = hkcu.open_subkey(REG_PATH) {
        let enabled: u32 = k.get_value("ProxyEnable").unwrap_or(0);
        let server: String = k.get_value("ProxyServer").unwrap_or_default();
        return enabled == 1 && server.contains("rlwy.net");
    }
    false
}

#[tauri::command]
fn enable_proxy() -> Result<(), String> {
    let script = format!(r#"
$regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
Set-ItemProperty -Path $regPath -Name ProxyEnable -Value 1
Set-ItemProperty -Path $regPath -Name ProxyServer -Value "{host}:{port}"
Set-ItemProperty -Path $regPath -Name ProxyOverride -Value "localhost;127.0.0.1;<local>"
$sig = '[DllImport("wininet.dll")] public static extern bool InternetSetOption(IntPtr h, int o, IntPtr b, int l);'
$t = Add-Type -MemberDefinition $sig -Name WinINet -Namespace Win32 -PassThru -EA SilentlyContinue
$t::InternetSetOption([IntPtr]::Zero, 39, [IntPtr]::Zero, 0) | Out-Null
$t::InternetSetOption([IntPtr]::Zero, 37, [IntPtr]::Zero, 0) | Out-Null
Write-Host "PROXY_OK"
"#, host = PROXY_HOST, port = PROXY_PORT);
    let out = std::process::Command::new("powershell")
        .args(["-ExecutionPolicy", "Bypass", "-Command", &script])
        .output()
        .map_err(|e| e.to_string())?;
    let stdout = String::from_utf8_lossy(&out.stdout);
    if !stdout.contains("PROXY_OK") {
        return Err(format!("Proxy enable failed: {}", stdout));
    }
    Ok(())
}

#[tauri::command]
fn disable_proxy() -> Result<(), String> {
    let script = r#"
$regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
Set-ItemProperty -Path $regPath -Name ProxyEnable -Value 0
$sig = '[DllImport("wininet.dll")] public static extern bool InternetSetOption(IntPtr h, int o, IntPtr b, int l);'
$t = Add-Type -MemberDefinition $sig -Name WinINet2 -Namespace Win32b -PassThru -EA SilentlyContinue
$t::InternetSetOption([IntPtr]::Zero, 39, [IntPtr]::Zero, 0) | Out-Null
$t::InternetSetOption([IntPtr]::Zero, 37, [IntPtr]::Zero, 0) | Out-Null
Write-Host "PROXY_OFF"
"#;
    std::process::Command::new("powershell")
        .args(["-ExecutionPolicy", "Bypass", "-Command", script])
        .output()
        .map_err(|e| e.to_string())?;
    Ok(())
}

fn refresh_wininet() {
    std::process::Command::new("powershell")
        .args([
            "-Command",
            r#"$t=Add-Type -MemberDefinition '[DllImport("wininet.dll")] public static extern bool InternetSetOption(IntPtr h,int o,IntPtr b,int l);' -Name W -Namespace N -PassThru -ErrorAction SilentlyContinue; $t::InternetSetOption(0,39,0,0); $t::InternetSetOption(0,37,0,0)"#,
        ])
        .output()
        .ok();
}

#[tauri::command]
fn install_cert(hub_url: String) -> Result<(), String> {
    disable_proxy().ok();
    // Use CurrentUser store — no admin rights needed, Chrome trusts it
    let script = format!(
        r#"
$ErrorActionPreference = 'Stop'
try {{
    $bytes = (Invoke-WebRequest '{}/cert' -UseBasicParsing).Content
    $pem = [System.Text.Encoding]::ASCII.GetString($bytes)
    $b64 = ($pem -replace '-----BEGIN CERTIFICATE-----','') -replace '-----END CERTIFICATE-----','' -replace '\s',''
    $der = [Convert]::FromBase64String($b64)
    $c = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2(,$der)
    $s = New-Object System.Security.Cryptography.X509Certificates.X509Store('Root','CurrentUser')
    $s.Open('ReadWrite')
    $s.Add($c)
    $s.Close()
    Write-Host "CERT_OK"
}} catch {{
    Write-Host "CERT_FAIL: $($_.Exception.Message)"
}}
"#,
        hub_url
    );
    let out = std::process::Command::new("powershell")
        .args(["-ExecutionPolicy", "Bypass", "-Command", &script])
        .output()
        .map_err(|e| e.to_string())?;
    let stdout = String::from_utf8_lossy(&out.stdout);
    if stdout.contains("CERT_FAIL") {
        return Err(format!("Cert install failed: {}", stdout));
    }
    Ok(())
}

// Tests the full chain FROM THIS MACHINE: proxy → mitmproxy → Google
// Uses WinHTTP (PowerShell) which respects Windows proxy + cert store.
// Returns "LOGGED_IN", "NOT_LOGGED_IN:<url>", or "ERROR:<msg>"
#[tauri::command]
fn test_connection() -> String {
    let script = r#"
try {
    $r = Invoke-WebRequest 'https://myaccount.google.com/' -UseBasicParsing -MaximumRedirection 10 -TimeoutSec 15
    $final = $r.BaseResponse.ResponseUri.ToString()
    if ($final -match 'myaccount\.google\.com') {
        Write-Host 'LOGGED_IN'
    } else {
        Write-Host "NOT_LOGGED_IN:$final"
    }
} catch {
    Write-Host "ERROR:$($_.Exception.Message)"
}
"#;
    std::process::Command::new("powershell")
        .args(["-ExecutionPolicy", "Bypass", "-Command", script])
        .output()
        .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        .unwrap_or_else(|e| format!("ERROR:{}", e))
}

// ── App entry ─────────────────────────────────────────────────────────────────

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            get_accounts,
            add_account,
            update_cookies,
            set_active_account,
            delete_account,
            get_proxy_status,
            get_cert_status,
            test_connection,
            enable_proxy,
            disable_proxy,
            install_cert,
        ])
        // Only Google traffic goes through proxy — see PAC file at /proxy.pac
        .run(tauri::generate_context!())
        .expect("error running tauri application");
}

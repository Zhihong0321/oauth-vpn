const invoke = window.__TAURI__.core.invoke;

let appData = { accounts: [], active_account_id: null, hub_url: '' };
let editingId = null;

// ── Status state — tracks real values, never fakes ───────────────────────────
const status = { cert: null, proxy: null, cookies: 0, login: null };

window.addEventListener('DOMContentLoaded', async () => {
  appData = await invoke('get_accounts');
  renderCards();
  await recheckAll();

  document.getElementById('fix-cert').onclick   = () => fixCert();
  document.getElementById('fix-proxy').onclick  = () => fixProxy();
  document.getElementById('fix-cookies').onclick = () => showAddForm();
  document.getElementById('fix-login').onclick  = () => reauthFlow();
});

// ── Recheck everything ────────────────────────────────────────────────────────
window.recheckAll = async function() {
  setRow('cert',    'checking', 'Checking Windows cert store…');
  setRow('proxy',   'checking', 'Checking registry…');
  setRow('cookies', 'checking', 'Checking hub…');
  setRow('login',   'checking', 'Waiting…');

  await checkCert();
  await checkProxy();
  await checkCookies();

  // Only run login check if cert + proxy + cookies are all good
  if (status.cert && status.proxy && status.cookies > 0) {
    await checkLogin();
  } else {
    const missing = [];
    if (!status.cert)        missing.push('cert not installed');
    if (!status.proxy)       missing.push('proxy not active');
    if (status.cookies === 0) missing.push('no cookies in hub');
    setRow('login', 'err', `Cannot check — fix above first: ${missing.join(', ')}`);
  }
};

async function checkCert() {
  try {
    const ok = await invoke('get_cert_status');
    status.cert = ok;
    if (ok) {
      setRow('cert', 'ok', 'Installed in Windows trusted root store');
      hide('fix-cert');
    } else {
      setRow('cert', 'err', '❌ NOT installed — Chrome cannot HTTPS through proxy without this');
      show('fix-cert');
    }
  } catch (e) {
    status.cert = false;
    setRow('cert', 'err', `❌ Check failed: ${e}`);
    show('fix-cert');
  }
}

async function checkProxy() {
  try {
    const ok = await invoke('get_proxy_status');
    status.proxy = ok;
    if (ok) {
      setRow('proxy', 'ok', 'Active → tramway.proxy.rlwy.net:25307');
      hide('fix-proxy');
    } else {
      setRow('proxy', 'err', '❌ Disabled — traffic not going through mitmproxy');
      show('fix-proxy');
    }
  } catch (e) {
    status.proxy = false;
    setRow('proxy', 'err', `❌ Check failed: ${e}`);
    show('fix-proxy');
  }
}

async function checkCookies() {
  try {
    const r = await fetch(appData.hub_url + '/status');
    const s = await r.json();
    status.cookies = s.cookie_count || 0;
    if (s.ok && status.cookies > 0) {
      setRow('cookies', 'ok', `${status.cookies} cookies in hub (source: ${s.source})`);
      hide('fix-cookies');
    } else {
      setRow('cookies', 'err', '❌ No cookies in hub — upload via Edit profile');
      show('fix-cookies');
    }
  } catch (e) {
    status.cookies = 0;
    setRow('cookies', 'err', `❌ Hub unreachable: ${e}`);
    show('fix-cookies');
  }
}

async function checkLogin() {
  setRow('login', 'checking', 'Testing through proxy from YOUR machine (takes ~10s)…');
  try {
    const result = await invoke('test_connection');
    status.login = result === 'LOGGED_IN';
    if (result === 'LOGGED_IN') {
      setRow('login', 'ok', '✅ Google confirmed — your machine is logged in through the proxy');
      hide('fix-login');
    } else if (result.startsWith('NOT_LOGGED_IN:')) {
      const url = result.replace('NOT_LOGGED_IN:', '');
      setRow('login', 'err', `❌ Cookies rejected by Google — redirected to: ${url}`);
      show('fix-login');
    } else {
      // ERROR:... — usually cert not trusted or proxy not reachable
      const msg = result.replace('ERROR:', '');
      setRow('login', 'err', `❌ Connection failed: ${msg}`);
      show('fix-login');
    }
  } catch (e) {
    status.login = false;
    setRow('login', 'err', `❌ Test failed: ${e}`);
    show('fix-login');
  }
}

// ── Fix actions ───────────────────────────────────────────────────────────────
window.connectAll = async function() {
  addLog('Starting full connect sequence…', 'info');
  await fixCert();
  await fixProxy();
  // recheck cookies — can't fix automatically, user must upload
  await checkCookies();
  if (status.cert && status.proxy && status.cookies > 0) {
    await checkLogin();
  }
};

async function fixCert() {
  setRow('cert', 'checking', 'Installing certificate…');
  try {
    await invoke('install_cert', { hubUrl: appData.hub_url });
    addLog('CA certificate installed', 'ok');
    await checkCert();
  } catch (e) {
    setRow('cert', 'err', `❌ Install failed: ${e}`);
    addLog(`Cert install failed: ${e}`, 'err');
  }
}

async function fixProxy() {
  setRow('proxy', 'checking', 'Enabling proxy…');
  try {
    await invoke('enable_proxy');
    addLog('Proxy enabled', 'ok');
    await checkProxy();
  } catch (e) {
    setRow('proxy', 'err', `❌ Failed: ${e}`);
    addLog(`Proxy failed: ${e}`, 'err');
  }
}

window.reauthFlow = async function() {
  addLog('Opening browser for re-authentication…', 'info');
  addLog('Sign in → Cookie-Editor → Export as JSON → Edit profile → Save', 'warn');
  window.open('https://gemini.google.com/app', '_blank');
};

// ── Profile cards ─────────────────────────────────────────────────────────────
async function reload() {
  appData = await invoke('get_accounts');
  renderCards();
}

function renderCards() {
  const list = document.getElementById('card-list');
  if (!appData.accounts.length) {
    list.innerHTML = '<div class="empty-state">No profiles yet — click + Add Profile to get started.</div>';
    return;
  }
  list.innerHTML = appData.accounts.map(acct => {
    const cookieCount = acct.cookies?.length ?? 0;
    const isActive = acct.id === appData.active_account_id;
    return `
    <div class="profile-card ${isActive ? 'active' : ''}" id="card-${acct.id}">
      <div class="card-info">
        <div class="card-label">${esc(acct.label)}</div>
        <div class="card-email">${esc(acct.email)}</div>
        <div class="card-cookies">${cookieCount > 0 ? `${cookieCount} cookies stored` : '⚠ No cookies'}</div>
      </div>
      <div class="card-actions">
        <button class="btn-icon" onclick="activateProfile('${acct.id}')">${isActive ? '✅ Active' : 'Set Active'}</button>
        <button class="btn-icon" onclick="editProfile('${acct.id}')">Edit</button>
        <button class="btn-icon del" onclick="deleteProfile('${acct.id}')">✕</button>
      </div>
    </div>`;
  }).join('');
}

window.activateProfile = async function(id) {
  try {
    await invoke('set_active_account', { accountId: id });
    addLog('Profile activated — cookies synced to hub', 'ok');
    await reload();
    await checkCookies();
    if (status.cert && status.proxy) await checkLogin();
  } catch (e) {
    addLog(`Activate failed: ${e}`, 'err');
  }
};

// ── Add / Edit form ───────────────────────────────────────────────────────────
window.showAddForm = function() {
  editingId = null;
  document.getElementById('form-title').textContent = 'New Profile';
  document.getElementById('form-label').value = '';
  document.getElementById('form-email').value = '';
  document.getElementById('form-cookies').value = '';
  document.getElementById('form-msg').textContent = '';
  document.getElementById('profile-form').classList.remove('hidden');
  document.getElementById('form-label').focus();
};

window.editProfile = function(id) {
  const acct = appData.accounts.find(a => a.id === id);
  if (!acct) return;
  editingId = id;
  document.getElementById('form-title').textContent = `Edit — ${acct.label}`;
  document.getElementById('form-label').value = acct.label;
  document.getElementById('form-email').value = acct.email;
  document.getElementById('form-cookies').value = '';
  document.getElementById('form-msg').textContent = '';
  document.getElementById('profile-form').classList.remove('hidden');
  document.getElementById('form-cookies').focus();
};

window.hideForm = function() {
  document.getElementById('profile-form').classList.add('hidden');
  editingId = null;
};

window.saveProfile = async function() {
  const label  = document.getElementById('form-label').value.trim();
  const email  = document.getElementById('form-email').value.trim();
  const raw    = document.getElementById('form-cookies').value.trim();
  const msgEl  = document.getElementById('form-msg');

  if (!label) { msgEl.style.color = '#e74c3c'; msgEl.textContent = 'Label required'; return; }

  try {
    let id = editingId;
    if (!id) {
      id = await invoke('add_account', { label, email });
    }
    if (raw) {
      const parsed = JSON.parse(raw);
      await invoke('update_cookies', { accountId: id, cookies: parsed });
      msgEl.style.color = '#2ecc71';
      msgEl.textContent = `✅ ${parsed.length} cookies saved`;
    } else {
      msgEl.style.color = '#2ecc71';
      msgEl.textContent = '✅ Profile saved';
    }
    await reload();
    await checkCookies();
    setTimeout(hideForm, 800);
  } catch (e) {
    msgEl.style.color = '#e74c3c';
    msgEl.textContent = '❌ ' + e;
  }
};

window.deleteProfile = async function(id) {
  if (!confirm('Delete this profile?')) return;
  await invoke('delete_account', { accountId: id });
  await reload();
};

// ── Status row helpers ────────────────────────────────────────────────────────
function setRow(key, state, detail) {
  const row = document.getElementById(`s-${key}`);
  if (!row) return;
  const icons = { ok: '✅', err: '❌', checking: '⏳', warn: '⚠️' };
  row.querySelector('.s-icon').textContent = icons[state] || '⏳';
  row.querySelector('.s-detail').textContent = detail;
  row.className = `status-row ${state}`;
  if (state === 'ok' || state === 'err') addLog(`[${key}] ${detail}`, state === 'ok' ? 'ok' : 'err');
}

function show(id) { document.getElementById(id)?.classList.remove('hidden'); }
function hide(id) { document.getElementById(id)?.classList.add('hidden'); }

// ── Log panel ─────────────────────────────────────────────────────────────────
function addLog(msg, type = 'info') {
  const out = document.getElementById('log-output');
  if (!out) return;
  const t = new Date().toLocaleTimeString();
  const el = document.createElement('div');
  el.className = `log-line ${type}`;
  el.textContent = `[${t}] ${msg}`;
  out.appendChild(el);
  out.scrollTop = out.scrollHeight;
}
window.clearLog = function() {
  document.getElementById('log-output').innerHTML = '';
};

// ── Utils ─────────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

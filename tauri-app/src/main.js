const invoke = window.__TAURI__.core.invoke;

let appData = { accounts: [], active_account_id: null, hub_url: '' };
let cardStatus = {}; // id → 'idle' | 'checking' | 'verified' | 'rejected'
let editingId = null;

function setCardStatus(id, status) {
  cardStatus[id] = status;
  renderCards();
}

// mode: 'admin' = manages cookies | 'user' = just connects proxy
const IS_ADMIN = true; // set false when distributing to team members

window.addEventListener('DOMContentLoaded', async () => {
  await reload();

  // Show/hide admin controls based on mode
  document.querySelectorAll('.admin-only').forEach(el => {
    el.style.display = IS_ADMIN ? '' : 'none';
  });

  if (IS_ADMIN && appData.active_account_id) {
    try {
      await invoke('set_active_account', { accountId: appData.active_account_id });
      addLog('Cookies synced to Hub', 'ok');
    } catch (e) {
      addLog(`Sync failed: ${e}`, 'err');
    }
    await verifySession(appData.active_account_id);
  } else if (!IS_ADMIN) {
    addLog('User mode — proxy only, no cookie management', 'info');
  }
  checkHub();
});

async function reload() {
  appData = await invoke('get_accounts');
  renderCards();
}

// ── Render profile cards ──────────────────────────────────────────────────────
function renderCards() {
  const list = document.getElementById('card-list');
  if (!appData.accounts.length) {
    list.innerHTML = '<div class="empty-state">No profiles yet — click + Add Profile to get started.</div>';
    return;
  }

  list.innerHTML = appData.accounts.map(acct => {
    const s = cardStatus[acct.id] || 'idle';
    const cookieCount = acct.cookies?.length ?? 0;

    // dot and health text ONLY reflect verified state — never lies
    const dotClass = {
      verified: 'connected',
      checking: 'checking',
      rejected: 'no-cookie',
      idle:     cookieCount > 0 ? 'healthy' : 'no-cookie',
    }[s];

    const healthText = {
      verified: '✅ Logged in — Google confirmed',
      checking: '⏳ Verifying with Google…',
      rejected: '❌ Cookies rejected — click Re-authenticate',
      idle:     cookieCount > 0 ? `${cookieCount} cookies ready — click Connect` : '⚠ No cookies — edit to add',
    }[s];

    const healthClass = {
      verified: 'ok',
      checking: 'warn',
      rejected: 'bad',
      idle:     cookieCount > 0 ? 'info' : 'bad',
    }[s];

    const connectBtn = (s === 'verified' || s === 'checking')
      ? `<button class="btn-connect disconnect" onclick="disconnect('${acct.id}')">Disconnect</button>`
      : s === 'rejected'
        ? `<button class="btn-connect reauth" onclick="reauthProfile('${acct.id}')">🔑 Re-authenticate</button>`
        : `<button class="btn-connect" onclick="connectProfile('${acct.id}')">Connect</button>`;

    return `
    <div class="profile-card ${s === 'verified' ? 'connected' : ''}" id="card-${acct.id}">
      <div class="card-dot ${dotClass}"></div>
      <div class="card-info">
        <div class="card-label">${esc(acct.label)}</div>
        <div class="card-email">${esc(acct.email)}</div>
        <div class="card-health ${healthClass}">${healthText}</div>
      </div>
      <div class="card-actions">
        ${connectBtn}
        ${IS_ADMIN ? `<button class="btn-icon" onclick="editProfile('${acct.id}')">Edit</button>` : ''}
        ${IS_ADMIN ? `<button class="btn-icon del" onclick="deleteProfile('${acct.id}')">✕</button>` : ''}
      </div>
    </div>`;
  }).join('');
}

// ── Connect / Disconnect ──────────────────────────────────────────────────────
window.connectProfile = async function(id) {
  const acct = appData.accounts.find(a => a.id === id);
  if (!acct) return;

  // Instant UI feedback — no waiting
  const btn = document.querySelector(`#card-${id} .btn-connect`);
  if (btn) { btn.textContent = '⏳'; btn.disabled = true; }
  setHubPill('grey', 'Connecting…');

  try {
    await invoke('install_cert', { hubUrl: appData.hub_url });
    addLog('CA certificate installed', 'ok');
  } catch (e) { addLog('Cert install skipped (already installed)', 'info'); }

  try {
    await invoke('enable_proxy');
    addLog(`Proxy enabled → tramway.proxy.rlwy.net:25307`, 'ok');
  } catch (e) {
    addLog(`Proxy failed: ${e}`, 'err');
    return;
  }

  appData.active_account_id = id;
  renderCards();

  try {
    if (IS_ADMIN) {
      // Admin only: push cookies to Hub
      await invoke('set_active_account', { accountId: id });
      addLog(`Cookies synced to Hub — ${acct.cookies?.length ?? 0} cookies`, 'ok');
    } else {
      addLog('User mode — using existing Hub cookies', 'info');
    }
    await verifySession(id);
  } catch (e) {
    addLog(`Error: ${e}`, 'err');
    setHubPill('yellow', '⚠ Proxy on, Hub sync failed');
  }
};

window.disconnect = async function(id) {
  await invoke('disable_proxy');
  appData.active_account_id = null;
  if (id) setCardStatus(id, 'idle');
  else { cardStatus = {}; renderCards(); }
  setHubPill('grey', 'Disconnected');
  addLog('Proxy disabled', 'warn');
};

// ── Hub status ────────────────────────────────────────────────────────────────
async function checkHub() {
  try {
    const r = await fetch(appData.hub_url + '/status');
    const s = await r.json();
    if (s.ok) {
      setHubPill('green', `Hub ✅ ${s.cookie_count} cookies`);
    } else {
      setHubPill('yellow', 'Hub online — no cookies');
    }
  } catch (_) {
    setHubPill('red', 'Hub unreachable');
  }
}

function setHubPill(color, text) {
  const el = document.getElementById('hub-pill');
  el.className = `pill ${color}`;
  el.textContent = text;
}

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
    setTimeout(hideForm, 800);
  } catch (e) {
    msgEl.style.color = '#e74c3c';
    msgEl.textContent = '❌ ' + e;
  }
};

async function verifySession(id) {
  setCardStatus(id, 'checking');
  setHubPill('yellow', '⏳ Asking Google…');
  addLog('Verifying with Google — waiting for real answer…', 'info');
  try {
    const r = await fetch(appData.hub_url + '/api/check-session');
    const result = await r.json();
    if (result.logged_in) {
      setCardStatus(id, 'verified');
      setHubPill('green', '✅ Logged in');
      addLog('✅ REAL GREEN — Google confirmed login', 'ok');
    } else {
      setCardStatus(id, 'rejected');
      setHubPill('red', '❌ Cookies rejected');
      addLog('❌ Google rejected cookies — need re-authenticate', 'err');
      addLog('Proxy is ON → open Chrome → gemini.google.com → Sign in → Cookie-Editor Export → Edit → Save', 'warn');
    }
  } catch (e) {
    setCardStatus(id, 'idle');
    setHubPill('yellow', '⚠ Could not verify');
    addLog(`Verification failed: ${e}`, 'warn');
  }
}

function showReauthButton(id) {
  const card = document.getElementById(`card-${id}`);
  if (!card || card.querySelector('.btn-reauth')) return;
  const btn = document.createElement('button');
  btn.className = 'btn-reauth';
  btn.textContent = '🔑 Re-authenticate';
  btn.onclick = () => reauthProfile(id);
  card.querySelector('.card-actions').prepend(btn);
}

window.reauthProfile = function(id) {
  // Open browser to Gemini WITH proxy active — user signs in from Railway IP
  // This creates cookies bound to Railway's IP which will work permanently
  addLog('Opening browser → sign in → Cookie-Editor Export → paste into Edit', 'warn');
  window.open('https://gemini.google.com/app', '_blank');
};

window.deleteProfile = async function(id) {
  if (!confirm('Delete this profile?')) return;
  await invoke('delete_account', { accountId: id });
  await reload();
};

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

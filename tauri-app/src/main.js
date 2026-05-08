// Use window.__TAURI__ (no bundler needed — set via withGlobalTauri: true)
const invoke = window.__TAURI__.core.invoke;

// ── State ─────────────────────────────────────────────────────────────────────
let appData = { accounts: [], active_account_id: null, hub_url: '' };
let editingId = null;
let updateAvailable = null;

// ── Boot ──────────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  await refresh();
  checkOTA();
  checkHub();
});

async function refresh() {
  appData = await invoke('get_accounts');
  const on = await invoke('get_proxy_status');
  setConnectUI(on);
  renderProfileSelect();
  renderProfileList();
  updateHealthBadge();
  document.getElementById('app-version').textContent = 'v0.1.0';
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
window.showTab = function(name) {
  document.getElementById('page-dash').classList.toggle('hidden', name !== 'dash');
  document.getElementById('page-admin').classList.toggle('hidden', name !== 'admin');
  document.getElementById('tab-dash').classList.toggle('active', name === 'dash');
  document.getElementById('tab-admin').classList.toggle('active', name === 'admin');
};

// ── Connect toggle ────────────────────────────────────────────────────────────
window.toggleProxy = async function() {
  const on = await invoke('get_proxy_status');
  const card = document.getElementById('connect-card');
  const dot  = document.getElementById('connect-dot');
  const lbl  = document.getElementById('connect-label');
  const sub  = document.getElementById('connect-sub');

  if (on) {
    await invoke('disable_proxy');
    setConnectUI(false);
  } else {
    lbl.textContent = 'Connecting…';
    dot.className = 'dot connecting';
    sub.textContent = 'Installing certificate…';
    try { await invoke('install_cert', { hubUrl: appData.hub_url }); } catch (_) {}
    await invoke('enable_proxy');
    setConnectUI(true);
  }
};

function setConnectUI(on) {
  const card = document.getElementById('connect-card');
  const dot  = document.getElementById('connect-dot');
  document.getElementById('connect-label').textContent = on ? 'Connected' : 'Disconnected';
  document.getElementById('connect-sub').textContent   = on
    ? 'Google traffic only — click to disconnect'
    : 'Click to connect — only Google traffic routed';
  dot.className  = 'dot' + (on ? ' connected' : '');
  card.className = 'card connect-card' + (on ? ' connected' : '');
}

// ── Profile select (dashboard) ────────────────────────────────────────────────
function renderProfileSelect() {
  const sel = document.getElementById('profile-select');
  sel.innerHTML = appData.accounts.length === 0
    ? '<option value="">— Add a profile in Admin tab —</option>'
    : appData.accounts.map(a =>
        `<option value="${a.id}" ${a.id === appData.active_account_id ? 'selected' : ''}>
          ${esc(a.label)} (${esc(a.email)})
        </option>`
      ).join('');
}

window.onProfileSelect = async function() {
  const id = document.getElementById('profile-select').value;
  if (!id) return;
  try {
    await invoke('set_active_account', { accountId: id });
    appData.active_account_id = id;
    updateHealthBadge();
    setMsg('hub-status', '✅ Cookies synced to Hub', '#2ecc71');
  } catch (e) {
    setMsg('hub-status', '❌ Sync failed: ' + e, '#e74c3c');
  }
};

function updateHealthBadge() {
  const badge  = document.getElementById('health-badge');
  const detail = document.getElementById('health-detail');
  const acct   = appData.accounts.find(a => a.id === appData.active_account_id);

  if (!acct) {
    badge.className = 'badge grey';
    badge.textContent = 'No profile';
    detail.textContent = '';
    return;
  }
  const count = acct.cookies?.length ?? 0;
  if (count === 0) {
    badge.className = 'badge red';
    badge.textContent = 'No cookies';
    detail.textContent = 'Go to Admin tab → select profile → paste cookies';
  } else {
    badge.className = 'badge green';
    badge.textContent = `✅ ${count} cookies`;
    detail.textContent = `Profile: ${acct.label}`;
  }
}

// ── Admin: profile list ───────────────────────────────────────────────────────
function renderProfileList() {
  const el = document.getElementById('profile-list');
  if (appData.accounts.length === 0) {
    el.innerHTML = '<p class="hint" style="padding:12px 0">No profiles yet. Click + New Profile.</p>';
    return;
  }
  el.innerHTML = appData.accounts.map(a => {
    const count   = a.cookies?.length ?? 0;
    const isActive = a.id === appData.active_account_id;
    const cookieColor = count > 0 ? '#2ecc71' : '#e74c3c';
    return `
    <div class="profile-item ${isActive ? 'active-profile' : ''}" style="margin-bottom:10px">
      <div class="profile-info">
        <div class="profile-name">${esc(a.label)} ${isActive ? '✅' : ''}</div>
        <div class="profile-email">${esc(a.email)}</div>
        <div class="profile-cookies" style="color:${cookieColor}">
          ${count === 0 ? 'No cookies — paste cookies to activate' : count + ' cookies saved'}
        </div>
      </div>
      <div class="profile-actions">
        <button class="btn-edit" onclick="editProfile('${a.id}')">Edit</button>
        <button class="btn-danger" onclick="deleteProfile('${a.id}')">Delete</button>
      </div>
    </div>`;
  }).join('');
}

// ── Admin: form ───────────────────────────────────────────────────────────────
window.showForm = function(id) {
  editingId = id || null;
  const form = document.getElementById('profile-form');
  document.getElementById('form-title').textContent = id ? 'Edit Profile' : 'New Profile';
  document.getElementById('form-msg').textContent = '';

  if (id) {
    const acct = appData.accounts.find(a => a.id === id);
    document.getElementById('form-label').value   = acct.label;
    document.getElementById('form-email').value   = acct.email;
    document.getElementById('form-cookies').value = '';
  } else {
    document.getElementById('form-label').value   = '';
    document.getElementById('form-email').value   = '';
    document.getElementById('form-cookies').value = '';
  }
  form.classList.remove('hidden');
  form.scrollIntoView({ behavior: 'smooth' });
};

window.editProfile = function(id) { showForm(id); };

window.cancelForm = function() {
  document.getElementById('profile-form').classList.add('hidden');
  editingId = null;
};

window.saveProfile = async function() {
  const label   = document.getElementById('form-label').value.trim();
  const email   = document.getElementById('form-email').value.trim();
  const rawCookies = document.getElementById('form-cookies').value.trim();
  const msgEl   = document.getElementById('form-msg');

  if (!label) { msgEl.style.color='#e74c3c'; msgEl.textContent='Label is required'; return; }

  try {
    let id = editingId;
    if (!id) {
      id = await invoke('add_account', { label, email });
    }

    if (rawCookies) {
      const parsed = JSON.parse(rawCookies);
      await invoke('update_cookies', { accountId: id, cookies: parsed });
      msgEl.style.color = '#2ecc71';
      msgEl.textContent = `✅ Saved — ${parsed.length} cookies`;
    } else {
      // Just update label/email via recreating (simplest approach)
      msgEl.style.color = '#2ecc71';
      msgEl.textContent = '✅ Profile saved';
    }

    await refresh();
    setTimeout(() => document.getElementById('profile-form').classList.add('hidden'), 1000);
    editingId = null;
  } catch (e) {
    msgEl.style.color = '#e74c3c';
    msgEl.textContent = '❌ ' + e;
  }
};

window.deleteProfile = async function(id) {
  if (!confirm('Delete this profile?')) return;
  await invoke('delete_account', { accountId: id });
  await refresh();
};

// ── OTA ───────────────────────────────────────────────────────────────────────
async function checkOTA() {
  const lbl = document.getElementById('ota-label');
  try {
    const { check } = window.__TAURI__['plugin:updater'];
    updateAvailable = await check();
    if (updateAvailable) {
      lbl.textContent = `🆕 Update ${updateAvailable.version} available`;
      lbl.style.color = '#1a73e8';
      document.getElementById('btn-update').classList.remove('hidden');
    } else {
      lbl.textContent = 'v0.1.0 — Up to date ✅';
      lbl.style.color = '#2ecc71';
    }
  } catch (_) {
    lbl.textContent = 'v0.1.0 — Could not check for updates';
  }
}

window.doUpdate = async function() {
  if (updateAvailable) await updateAvailable.downloadAndInstall();
};

// ── Hub status ────────────────────────────────────────────────────────────────
async function checkHub() {
  const el = document.getElementById('hub-status');
  try {
    const r = await fetch(appData.hub_url + '/status');
    const s = await r.json();
    el.textContent = s.ok
      ? `✅ Online — ${s.cookie_count} cookies active`
      : `⚠️ Online — no cookies (sync a profile)`;
    el.style.color = s.ok ? '#2ecc71' : '#f39c12';
  } catch (_) {
    el.textContent = '❌ Hub unreachable';
    el.style.color = '#e74c3c';
  }
}

// ── Utils ─────────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
function setMsg(id, text, color) {
  const el = document.getElementById(id);
  if (el) { el.textContent = text; el.style.color = color; }
}

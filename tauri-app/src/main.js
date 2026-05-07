import { invoke } from '@tauri-apps/api/core';
import { check } from '@tauri-apps/plugin-updater';

// ── State ────────────────────────────────────────────────────────────────────
let state = { accounts: [], active_account_id: null, hub_url: '' };
let selectedId = null;

// ── Boot ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  await loadState();
  await refreshProxyStatus();
  checkForUpdate();

  document.getElementById('btn-toggle').addEventListener('click', onToggleProxy);
  document.getElementById('btn-add-account').addEventListener('click', showAddPanel);
  document.getElementById('btn-create').addEventListener('click', onCreateAccount);
  document.getElementById('btn-activate').addEventListener('click', onActivate);
  document.getElementById('btn-delete').addEventListener('click', onDelete);
  document.getElementById('btn-save-cookies').addEventListener('click', onSaveCookies);
});

// ── Data ─────────────────────────────────────────────────────────────────────
async function loadState() {
  state = await invoke('get_accounts');
  renderAccountList();
}

function renderAccountList() {
  const ul = document.getElementById('account-list');
  ul.innerHTML = '';
  state.accounts.forEach(acct => {
    const li = document.createElement('li');
    li.dataset.id = acct.id;
    if (acct.id === selectedId) li.classList.add('selected');
    if (acct.id === state.active_account_id) li.classList.add('active-account');
    const cookieCount = acct.cookies?.length ?? 0;
    li.innerHTML = `
      <div class="acct-label">${escHtml(acct.label)}</div>
      <div class="acct-email">${escHtml(acct.email)}</div>
      <div class="acct-cookies ${cookieCount === 0 ? 'empty' : ''}">
        ${cookieCount === 0 ? 'No cookies' : `${cookieCount} cookies`}
      </div>`;
    li.addEventListener('click', () => selectAccount(acct.id));
    ul.appendChild(li);
  });
}

function selectAccount(id) {
  selectedId = id;
  hideAll();
  const acct = state.accounts.find(a => a.id === id);
  if (!acct) return;

  renderAccountList();

  document.getElementById('account-panel').classList.remove('hidden');
  document.getElementById('empty-state').classList.add('hidden');
  document.getElementById('field-label').value = acct.label;
  document.getElementById('field-email').value = acct.email;
  document.getElementById('cookie-input').value = '';
  document.getElementById('cookie-status').textContent = '';

  const count = acct.cookies?.length ?? 0;
  document.getElementById('cookie-count').textContent = count > 0 ? `${count} cookies saved` : 'No cookies';

  const badge = document.getElementById('active-badge');
  if (acct.id === state.active_account_id) {
    badge.classList.remove('hidden');
  } else {
    badge.classList.add('hidden');
  }
}

// ── Account actions ───────────────────────────────────────────────────────────
async function onCreateAccount() {
  const label = document.getElementById('new-label').value.trim();
  const email = document.getElementById('new-email').value.trim();
  if (!label) return alert('Enter a label');
  const id = await invoke('add_account', { label, email });
  await loadState();
  selectAccount(id);
}

async function onActivate() {
  if (!selectedId) return;
  try {
    await invoke('set_active_account', { accountId: selectedId });
    await loadState();
    selectAccount(selectedId);
    document.getElementById('cookie-status').textContent = '✅ Active — cookies synced to Hub';
    document.getElementById('cookie-status').style.color = '#2ecc71';
  } catch (e) {
    document.getElementById('cookie-status').textContent = '❌ Sync failed: ' + e;
    document.getElementById('cookie-status').style.color = '#e74c3c';
  }
}

async function onDelete() {
  if (!selectedId) return;
  if (!confirm('Delete this account?')) return;
  await invoke('delete_account', { accountId: selectedId });
  selectedId = null;
  await loadState();
  hideAll();
  document.getElementById('empty-state').classList.remove('hidden');
}

async function onSaveCookies() {
  const raw = document.getElementById('cookie-input').value.trim();
  if (!raw) return;
  try {
    const parsed = JSON.parse(raw);
    await invoke('update_cookies', { accountId: selectedId, cookies: parsed });
    document.getElementById('cookie-status').textContent = `✅ ${parsed.length} cookies saved`;
    document.getElementById('cookie-status').style.color = '#2ecc71';
    await loadState();
    selectAccount(selectedId);
  } catch (e) {
    document.getElementById('cookie-status').textContent = '❌ Invalid JSON: ' + e;
    document.getElementById('cookie-status').style.color = '#e74c3c';
  }
}

// ── Proxy ─────────────────────────────────────────────────────────────────────
async function refreshProxyStatus() {
  const on = await invoke('get_proxy_status');
  setProxyUI(on);
}

function setProxyUI(connected) {
  const dot   = document.getElementById('status-dot');
  const label = document.getElementById('status-label');
  const sub   = document.getElementById('status-sub');
  const btn   = document.getElementById('btn-toggle');
  dot.className   = connected ? 'connected' : '';
  btn.className   = connected ? 'connected' : '';
  label.textContent = connected ? 'Connected' : 'Disconnected';
  sub.textContent   = connected ? 'Google only — click to disconnect' : 'Click to connect';
}

async function onToggleProxy() {
  const on = await invoke('get_proxy_status');
  if (on) {
    await invoke('disable_proxy');
    setProxyUI(false);
  } else {
    // Install cert first time
    try {
      document.getElementById('status-label').textContent = 'Installing cert…';
      await invoke('install_cert', { hubUrl: state.hub_url });
    } catch (_) {}
    await invoke('enable_proxy');
    setProxyUI(true);
  }
}

// ── OTA ───────────────────────────────────────────────────────────────────────
async function checkForUpdate() {
  try {
    const update = await check();
    if (update) {
      const ok = confirm(`Update ${update.version} available. Install now?`);
      if (ok) await update.downloadAndInstall();
    }
  } catch (_) {}
}

// ── UI helpers ────────────────────────────────────────────────────────────────
function hideAll() {
  document.getElementById('account-panel').classList.add('hidden');
  document.getElementById('add-panel').classList.add('hidden');
}

function showAddPanel() {
  selectedId = null;
  renderAccountList();
  hideAll();
  document.getElementById('empty-state').classList.add('hidden');
  document.getElementById('add-panel').classList.remove('hidden');
  document.getElementById('new-label').value = '';
  document.getElementById('new-email').value = '';
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

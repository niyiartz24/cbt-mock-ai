// ============================================================
// CBT Mock AI — Frontend API Configuration
// Update API_BASE when deploying to production
// ============================================================

const CONFIG = {
  API_BASE: 'https://cbt-mock-ai.onrender.com/api',
  // Example production: API_BASE: 'https://cbt-mock-api.onrender.com/api',
};

// ── Storage helpers ──────────────────────────────────────────
const Storage = {
  getToken:    () => localStorage.getItem('cbt_admin_token'),
  setToken:    (t) => localStorage.setItem('cbt_admin_token', t),
  removeToken: () => localStorage.removeItem('cbt_admin_token'),
  getTheme:    () => localStorage.getItem('cbt_theme') || 'dark',
  setTheme:    (t) => localStorage.setItem('cbt_theme', t),
};

// ── API helpers ──────────────────────────────────────────────
const API = {
  async _request(path, options = {}) {
    const url = `${CONFIG.API_BASE}${path}`;
    const token = Storage.getToken();
    const headers = { ...options.headers };

    if (token && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    if (!(options.body instanceof FormData) && options.body && typeof options.body === 'object') {
      headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.body);
    }

    const res = await fetch(url, { ...options, headers });
    const data = await res.json().catch(() => ({ error: 'Invalid server response' }));

    if (!res.ok) {
      throw new APIError(data.error || `HTTP ${res.status}`, res.status, data);
    }

    return data;
  },

  get:    (path)         => API._request(path, { method: 'GET' }),
  post:   (path, body)   => API._request(path, { method: 'POST', body }),
  put:    (path, body)   => API._request(path, { method: 'PUT', body }),
  delete: (path)         => API._request(path, { method: 'DELETE' }),
  upload: (path, form)   => API._request(path, { method: 'POST', body: form }),
};

class APIError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

// ── Theme helper ─────────────────────────────────────────────
function applyTheme(theme) {
  document.body.classList.toggle('light-mode', theme === 'light');
  document.querySelectorAll('.theme-toggle').forEach(btn => {
    btn.textContent = theme === 'dark' ? '☀' : '☽';
    btn.title = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
  });
}

function initTheme() {
  applyTheme(Storage.getTheme());
}

function toggleTheme() {
  const next = Storage.getTheme() === 'dark' ? 'light' : 'dark';
  Storage.setTheme(next);
  applyTheme(next);
}

// ── Toast notifications ───────────────────────────────────────
function showToast(message, type = 'info', duration = 3500) {
  const existing = document.getElementById('cbt-toast');
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.id = 'cbt-toast';
  const colors = { success: '#22C55E', danger: '#EF4444', warning: '#F59E0B', info: '#6366F1' };
  toast.style.cssText = `
    position: fixed; bottom: 1.5rem; right: 1.5rem; z-index: 9999;
    background: var(--surface); border: 1px solid var(--border);
    border-left: 4px solid ${colors[type] || colors.info};
    padding: 0.85rem 1.25rem; border-radius: 8px;
    font-family: 'Sora', sans-serif; font-size: 0.875rem;
    color: var(--text); max-width: 340px; box-shadow: var(--shadow-lg);
    animation: slideUp 200ms ease; line-height: 1.5;
  `;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), duration);
}

// ── DOM helpers ───────────────────────────────────────────────
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

function html(strings, ...values) {
  return strings.reduce((acc, str, i) => acc + str + (values[i] !== undefined ? escapeHtml(String(values[i])) : ''), '');
}

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function setLoading(btn, loading, text) {
  if (!btn) return;
  btn.disabled = loading;
  if (loading) {
    btn._origText = btn.innerHTML;
    btn.innerHTML = `<span class="spinner"></span> ${text || 'Loading...'}`;
  } else {
    btn.innerHTML = btn._origText || text || btn.innerHTML;
  }
}

/**
 * common.js — Shared utilities for all Operations pages.
 * Loaded by base.html (as the first <script>) before any page-specific script.
 *
 * Server-side values (BASE_PATH, DEPARTMENTS, CAN_WRITE) are passed via
 * data-* attributes on this very <script> tag — no inline scripts required,
 * so there is no CSP 'unsafe-inline' violation.
 */

// ---------------------------------------------------------------------------
// Read server-injected globals from this script's own data-* attributes.
// The <script> tag has id="common-script" for reliable lookup.
// ---------------------------------------------------------------------------

(function () {
    const tag = document.getElementById('common-script')
             || document.currentScript;

    window.BASE_PATH   = (tag && tag.dataset.basePath)   || '';
    window.CAN_WRITE   = (tag && tag.dataset.canWrite)   === 'true';
    try {
        window.DEPARTMENTS = JSON.parse((tag && tag.dataset.departments) || '[]');
    } catch (_) {
        window.DEPARTMENTS = [];
    }
})();

// ---------------------------------------------------------------------------
// API fetch helper
// ---------------------------------------------------------------------------

async function apiFetch(path, options = {}) {
    const url = BASE_PATH + path;
    const res = await fetch(url, {
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
        ...options,
    });
    if (!res.ok) {
        let err = `HTTP ${res.status}`;
        try { const j = await res.json(); err = j.error || err; } catch (_) {}
        throw new Error(err);
    }
    if (res.status === 204) return null;
    return res.json();
}

// ---------------------------------------------------------------------------
// Toast notifications
// ---------------------------------------------------------------------------

function showToast(message, type = 'info', durationMs = 3500) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = 'toastOut 300ms forwards';
        setTimeout(() => toast.remove(), 320);
    }, durationMs);
}

// ---------------------------------------------------------------------------
// Debounce
// ---------------------------------------------------------------------------

function debounce(fn, ms = 250) {
    let t;
    return (...args) => {
        clearTimeout(t);
        t = setTimeout(() => fn(...args), ms);
    };
}

// ---------------------------------------------------------------------------
// Safe DOM builder — no innerHTML used for user data
// ---------------------------------------------------------------------------

function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
        if (k === 'cls')   node.className = v;
        else if (k === 'style') Object.assign(node.style, v);
        else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
        else node.setAttribute(k, v);
    }
    for (const child of children) {
        if (child == null) continue;
        node.append(typeof child === 'string' ? document.createTextNode(child) : child);
    }
    return node;
}

function txt(content) { return document.createTextNode(String(content ?? '')); }

// ---------------------------------------------------------------------------
// Department pill helper
// ---------------------------------------------------------------------------

function deptPill(dept) {
    const slug = (dept || '').toLowerCase().replace(/[\s/]+/g, '-');
    return el('span', { cls: `dept-pill dept-${slug}` }, dept);
}

// ---------------------------------------------------------------------------
// Time formatters
// ---------------------------------------------------------------------------

function fmtTime(isoStr) {
    if (!isoStr) return '—';
    return isoStr.substring(11, 16);  // HH:MM
}

function fmtTimeRange(start, end) {
    return `${fmtTime(start)}–${fmtTime(end)}`;
}

function fmtDate(isoStr) {
    if (!isoStr) return '';
    try {
        const d = new Date(isoStr);
        return d.toLocaleDateString('en-GB', { weekday: 'short', month: 'short', day: 'numeric' });
    } catch (_) { return isoStr.slice(0, 10); }
}

// ---------------------------------------------------------------------------
// Header initialisation — updates the cache status dot, event name badge,
// and conflict counter badge on every page load.
// Runs after the DOM is ready (this script is placed at end of <body>).
// ---------------------------------------------------------------------------

(async function initHeader() {
    // Health / cache status
    try {
        const h = await apiFetch('/api/health');
        const dot       = document.getElementById('cache-dot');
        const label     = document.getElementById('cache-label');
        const nameBadge = document.getElementById('event-name-badge');
        if (h.has_data) {
            if (dot)       dot.className     = 'status-dot ok';
            if (label)     label.textContent = h.schedule_version || 'live';
            if (nameBadge && h.event && h.event.name) nameBadge.textContent = h.event.name;
        } else {
            if (dot)   dot.className     = 'status-dot loading';
            if (label) label.textContent = h.error ? 'Error' : 'Loading';
        }
    } catch (_) { /* non-fatal */ }

    // Conflict badge on the Events nav link
    try {
        const c     = await apiFetch('/api/conflicts');
        const badge = document.getElementById('nav-conflict-badge');
        if (badge && c.total > 0) {
            badge.textContent = c.total;
            badge.classList.remove('hidden');
        }
    } catch (_) { /* non-fatal */ }
})();

// ---------------------------------------------------------------------------
// Mobile nav hamburger toggle (CSP-safe — lives in external script, not inline)
// ---------------------------------------------------------------------------

(function () {
    const btn      = document.getElementById('nav-hamburger');
    const dropdown = document.getElementById('mobile-nav-dropdown');
    if (!btn || !dropdown) return;

    function open() {
        dropdown.classList.remove('hidden');
        btn.setAttribute('aria-expanded', 'true');
        btn.classList.add('is-open');
    }
    function close() {
        dropdown.classList.add('hidden');
        btn.setAttribute('aria-expanded', 'false');
        btn.classList.remove('is-open');
    }

    btn.addEventListener('click', function (e) {
        e.stopPropagation();
        dropdown.classList.contains('hidden') ? open() : close();
    });

    document.addEventListener('click', function (e) {
        if (!dropdown.contains(e.target)) close();
    });

    // Mirror conflict badge count into mobile dropdown
    const desktopBadge = document.getElementById('nav-conflict-badge');
    const mobileBadge  = document.getElementById('mobile-conflict-badge');
    if (desktopBadge && mobileBadge) {
        new MutationObserver(function () {
            mobileBadge.textContent = desktopBadge.textContent;
            mobileBadge.classList.toggle('hidden', desktopBadge.classList.contains('hidden'));
        }).observe(desktopBadge, { childList: true, attributes: true, attributeFilter: ['class'] });
    }
}());

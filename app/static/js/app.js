// app/static/js/app.js
function exchangeDisplay(name) {
  if (!name) return '';
  return name.charAt(0).toUpperCase() + name.slice(1);
}

function exchangeIcon(name) {
  return `<span class="cell-exchange">${exchangeDisplay(name)}</span>`;
}

function tvUrl(exchange, symbol) {
  return `https://www.tradingview.com/chart/?symbol=${exchange.toUpperCase()}:${symbol}.P`;
}

// Link visibility prefs — refreshed on every poll cycle
const linkPrefs = { coinglass: true, tradingview: true };

function refreshLinkPrefs() {
  fetch('/api/settings/display', { cache: 'no-store' })
    .then(r => r.json())
    .then(data => {
      linkPrefs.coinglass = data.show_coinglass !== false;
      linkPrefs.tradingview = data.show_tradingview !== false;
    })
    .catch(() => {});
}
refreshLinkPrefs();

(function startSignalsLive() {
  let timer = null;
  let lastFp = null;
  let knownKeys = new Set();
  let currentPage = 1;

  function fmtTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
  }


  function fingerprint(list) {
    if (!Array.isArray(list) || !list.length) return 'empty';
    const head = list.slice(0, 5)
      .map(t => `${t.symbol}|${t.event_ts}|${t.pct}|${t.rule_name}`)
      .join(';');
    return `${list.length}:${head}`;
  }

  async function fetchSignals() {
    const resp = await fetch(`/api/signals?page=${currentPage}`, { cache: 'no-store' });
    if (!resp.ok) throw new Error('fetch failed');
    return await resp.json();
  }


  function rowDesktop(r) {
    const pct = (r.pct != null) ? Number(r.pct).toFixed(2) : '';
    const t = fmtTime(r.event_ts);
    const rLabel = r.rule_label || r.rule_name || '?';
    const rColor = r.rule_color || '#10b981';
    const exName = exchangeDisplay(r.exchange);

    return `
  <tr data-sig-key="${r.symbol}|${r.event_ts}">
    <td class="col-left cell-time">${t}</td>
    <td class="col-left cell-exchange">${exName}</td>
    <td class="col-left cell-symbol">${r.symbol}</td>
    <td class="col-center">
      <span class="rule-badge" style="--rule-color:${rColor}">${rLabel}</span>
    </td>
    <td class="cell-pct">${pct}%</td>
    <td class="cell-links"><div>
      ${linkPrefs.coinglass ? `<a target="_blank" href="https://www.coinglass.com/tv/${exName}_${r.symbol}" class="link-pill">Coinglass</a>` : ''}
      ${linkPrefs.tradingview ? `<a target="_blank" href="${tvUrl(r.exchange || 'bybit', r.symbol)}" class="link-pill">TradingView</a>` : ''}
      <a target="_blank" href="/go/exchange/${encodeURIComponent(r.exchange || 'bybit')}" class="link-pill">${exName}</a>
    </div></td>
  </tr>`;
  }

  function cardMobile(r) {
    const t = fmtTime(r.event_ts);
    const rLabel = r.rule_label || r.rule_name || '?';
    const rColor = r.rule_color || '#10b981';
    const exName = exchangeDisplay(r.exchange);

    return `
  <div class="signal-card" data-sig-key="${r.symbol}|${r.event_ts}">
    <div class="signal-card-row">
      <div class="signal-card-info">
        <span class="cell-time">[${t}]</span>
        <span class="cell-symbol text-truncate">${r.symbol}</span>
        <span class="rule-badge rule-badge-sm" style="--rule-color:${rColor}" title="${rLabel}">${rLabel}</span>
      </div>
      <div class="signal-card-links">
        ${linkPrefs.coinglass ? `<a href="https://www.coinglass.com/tv/${exName}_${r.symbol}" target="_blank" class="link-pill link-pill-sm">CG</a>` : ''}
        ${linkPrefs.tradingview ? `<a href="${tvUrl(r.exchange || 'bybit', r.symbol)}" target="_blank" class="link-pill link-pill-sm">TV</a>` : ''}
        <a href="/go/exchange/${encodeURIComponent(r.exchange || 'bybit')}" target="_blank" class="link-pill link-pill-sm">${exName}</a>
      </div>
    </div>
  </div>`;
  }



  function renderPagination(total, page, perPage) {
    const container = document.getElementById('signals-pagination');
    if (!container) return;
    const totalPages = Math.max(Math.ceil(total / perPage), 1);
    if (totalPages <= 1) { container.innerHTML = ''; return; }

    container.innerHTML = `
      <div class="pagination">
        <button data-action="page-prev" class="btn btn-ghost"
                ${page <= 1 ? 'disabled' : ''}>Prev</button>
        <span class="pagination-label">${page} / ${totalPages}</span>
        <button data-action="page-next" class="btn btn-ghost"
                ${page >= totalPages ? 'disabled' : ''}>Next</button>
      </div>`;
  }

  function render(items, total, page, perPage) {
    const newKeys = new Set(items.map(r => `${r.symbol}|${r.event_ts}`));
    const isFirstRender = knownKeys.size === 0;

    const tbody = document.getElementById('signals-desktop-body');
    const mlist = document.getElementById('signals-mobile-list');

    if (items.length === 0) {
      const emptyHtml = `<div class="empty-state">
        <img src="/static/images/chart.svg" alt="" class="empty-state-chart" aria-hidden="true">
        <p class="empty-state-text">Waiting for signals<span class="empty-state-dots"></span></p>
      </div>`;
      const empty = `<tr><td colspan="6" class="signal-table-empty">${emptyHtml}</td></tr>`;
      if (tbody) tbody.innerHTML = empty;
      if (mlist) mlist.innerHTML = `<div class="signal-table-empty">${emptyHtml}</div>`;
      document.querySelectorAll('[data-action="clear-signals"]').forEach(el => {
        el.classList.add('is-disabled');
        el.setAttribute('aria-disabled', 'true');
      });
    } else {
      if (tbody) tbody.innerHTML = items.map(rowDesktop).join('');
      if (mlist) mlist.innerHTML = items.map(cardMobile).join('');
      document.querySelectorAll('[data-action="clear-signals"]').forEach(el => {
        el.classList.remove('is-disabled');
        el.removeAttribute('aria-disabled');
      });
    }

    if (!isFirstRender) {
      document.querySelectorAll('[data-sig-key]').forEach(el => {
        const key = el.getAttribute('data-sig-key');
        if (!knownKeys.has(key)) el.classList.add('signal-flash');
      });
    }

    knownKeys = newKeys;
    renderPagination(total, page, perPage);
  }

  async function tick() {
    try {
      refreshLinkPrefs();
      const data = await fetchSignals();
      const items = data.signals || [];
      const fp = fingerprint(items);
      if (!lastFp || fp !== lastFp) render(items, data.total, data.page, data.per_page);
      lastFp = fp;
    } catch (e) {
      // silent
    }
  }

  // SSE: instant signal push (fallback to polling if SSE unavailable)
  let sseActive = false;
  function startSSE() {
    if (typeof EventSource === 'undefined') return;
    const es = new EventSource('/api/signals/stream');
    es.onopen = () => { sseActive = true; };
    es.onmessage = () => {
      // New signal arrived — do a full table refresh to keep pagination/order correct
      lastFp = null;
      tick();
    };
    es.onerror = () => {
      sseActive = false;
      es.close();
      // Reconnect after 5 seconds
      setTimeout(startSSE, 5000);
    };
  }
  startSSE();

  // Initial fetch — show empty state or signals immediately
  tick();

  // Fallback poll: runs every 5s only when SSE is down, or every 10s as heartbeat
  function schedulePoll() {
    const interval = sseActive ? 10000 : 5000;
    timer = setTimeout(() => { tick(); schedulePoll(); }, interval);
  }
  schedulePoll();

  document.addEventListener('click', (e) => {
    const prev = e.target.closest('[data-action="page-prev"]');
    const next = e.target.closest('[data-action="page-next"]');
    if (prev && currentPage > 1) { currentPage--; lastFp = null; tick(); }
    if (next) { currentPage++; lastFp = null; tick(); }

    const clearBtn = e.target.closest('[data-action="clear-signals"]');
    if (clearBtn) {
      e.preventDefault();
      showModal('Clear all signals?', { confirm: true, confirmLabel: 'Clear', danger: true }).then(ok => {
        if (!ok) return;
        fetch('/api/signals', {
          method: 'DELETE',
          headers: { 'X-CSRFToken': csrfToken() },
        }).then(r => { if (r.ok) { currentPage = 1; lastFp = null; tick(); } });
      });
    }
  });

  tick();
})();


// Hydrate server-rendered <time data-ts> as local HH:MM
(function () {
  function fmtHHMM(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
  }
  function hydrateServerTimes() {
    document.querySelectorAll('time[data-ts]').forEach(el => {
      const iso = el.getAttribute('data-ts');
      el.textContent = fmtHHMM(iso);
      // tooltip with full local date+time
      const d = new Date(iso);
      if (!Number.isNaN(d.getTime())) el.title = d.toLocaleString();
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', hydrateServerTimes);
  } else {
    hydrateServerTimes();
  }
})();

(function () {
  function tickClock() {
    const el = document.getElementById('local-clock');
    if (!el) return;
    el.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
  }
  window.addEventListener('load', tickClock);
  setInterval(tickClock, 60_000);
})();


// --- Footer status polling ---------------------------------------------------
const UI_STATUS_POLL_MS = 3000; // poll every 3s

function setBadge(elDot, elText, state, labelWhenUp, labelWhenDown) {
  if (!elDot || !elText) return;
  elDot.classList.remove("is-up", "is-down", "is-retry");
  elDot.className = "status-dot";
  if (state === "up") {
    elDot.classList.add("is-up");
    elText.textContent = labelWhenUp;
  } else if (state === "retry") {
    elDot.classList.add("is-retry");
    elText.textContent = labelWhenDown;
  } else {
    elDot.classList.add("is-down");
    elText.textContent = labelWhenDown;
  }
}

async function refreshFooterStatus() {
  const appDot = document.querySelector("[data-app-dot]");
  const appLabel = document.querySelector("[data-app-label]");
  const exDot = document.querySelector("[data-ex-dot]");
  const exLabel = document.querySelector("[data-ex-label]");

  try {
    const r1 = await fetch("/api/ping", { cache: "no-store" });
    if (r1.ok) {
      setBadge(appDot, appLabel, "up", "app", "app");

    } else {
      setBadge(appDot, appLabel, "down", "app", "app");
  
    }
  } catch (_) {
    setBadge(appDot, appLabel, "down", "app", "app");

  }

  const coinsLabel = document.querySelector("[data-coins-label]");
  const screenerDot = document.querySelector("[data-screener-dot]");
  const screenerLabel = document.querySelector("[data-screener-label]");

  try {
    const r2 = await fetch("/api/status", { cache: "no-store" });
    if (!r2.ok) throw new Error("status bad");
    const s = await r2.json();
    if (s.online) {
      setBadge(exDot, exLabel, "up", "bybit", "bybit");
    } else {
      if (s.reason === "network_down") {
        setBadge(exDot, exLabel, "down", "bybit", "bybit");
      } else {
        setBadge(exDot, exLabel, "retry", "bybit", "bybit");
      }
    }

    // Screener badge
    if (s.screener_alive) {
      setBadge(screenerDot, screenerLabel, "up", "screener", "screener");
    } else {
      setBadge(screenerDot, screenerLabel, "down", "screener", "screener");
    }

    // Update coins count (dash when screener offline, flash on change)
    if (coinsLabel) {
      const newText = s.screener_alive && s.active_count != null
        ? `coins: ${s.active_count}`
        : "coins: —";
      if (coinsLabel.textContent !== newText) {
        coinsLabel.textContent = newText;
        const badge = coinsLabel.closest('[data-coins-badge]');
        if (badge) {
          badge.classList.remove('coins-flash');
          void badge.offsetWidth;
          badge.classList.add('coins-flash');
        }
      }
    }
  } catch (_) {
    setBadge(exDot, exLabel, "down", "bybit", "bybit");
    setBadge(screenerDot, screenerLabel, "down", "screener", "screener");
  }
}

setInterval(refreshFooterStatus, UI_STATUS_POLL_MS);
window.addEventListener("load", refreshFooterStatus);


// --- Mute toggle -------------------------------------------------------------
(function initMuteToggle() {

  function updateMuteUI(muted) {
    const btn = document.querySelector('[data-action="mute-toggle"]');
    if (!btn) return;
    const icon = btn.querySelector('[data-mute-icon]');
    if (icon) {
      icon.className = muted ? "ri-volume-mute-line" : "ri-volume-up-line";
    }
    btn.title = muted ? "Sound muted" : "Sound on";
    btn.setAttribute("data-muted", muted ? "true" : "false");
  }

  async function pollMute() {
    try {
      const r = await fetch("/api/mute", { cache: "no-store" });
      if (r.ok) {
        const data = await r.json();
        updateMuteUI(data.muted);
      }
    } catch (_) { /* silent */ }
  }

  document.addEventListener("click", async (e) => {
    const btn = e.target.closest('[data-action="mute-toggle"]');
    if (!btn) return;
    try {
      const r = await fetch("/api/mute", {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken() },
      });
      if (r.ok) {
        const data = await r.json();
        updateMuteUI(data.muted);
      }
    } catch (_) { /* silent */ }
  });

  // Poll mute state alongside status polling
  setInterval(pollMute, UI_STATUS_POLL_MS);
  window.addEventListener("load", pollMute);
})();


// Copy-to-clipboard for [data-copy]
document.addEventListener('click', (e) => {
  const btn = e.target.closest('[data-copy]');
  if (!btn) return;
  const val = btn.getAttribute('data-copy');
  if (!val) return;
  navigator.clipboard.writeText(val).then(() => {
    const oldHTML = btn.innerHTML;
    btn.innerHTML = '<i class="ri-check-line" style="color: var(--emerald-400);"></i>';
    setTimeout(() => (btn.innerHTML = oldHTML), 1200);
  }).catch(() => { });
});


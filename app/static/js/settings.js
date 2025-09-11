// settings.js — Rule CRUD, settings save/reset, sound preview
// Depends on: helpers.js ($, $$, csrfToken, api, formatNumber, parseFormatted)
(function () {
  "use strict";

  // ---- DOM refs ----
  const rulesTbody = $('[data-el="rules-tbody"]');
  if (!rulesTbody) return;

  // ---- Exchange symbols cache (for validation & autocomplete) ----
  let knownSymbols = [];
  let knownSet = new Set();
  fetch("/api/symbols")
    .then((r) => r.json())
    .then((syms) => { knownSymbols = syms; knownSet = new Set(syms); })
    .catch(() => {});

  // ---- Color palette from hidden DOM ----
  const colorPalette = [];
  $$('[data-el="color-palette"] span').forEach(s => {
    colorPalette.push({ hex: s.dataset.color, name: s.dataset.name });
  });

  function colorPickerHtml(selectedHex) {
    const dots = colorPalette.map(c =>
      `<button type="button" class="rule-color-picker-option" data-action="inline-pick-color" data-color="${c.hex}" style="background:${c.hex};" title="${c.name}"></button>`
    ).join('');
    return `<div class="rule-color-picker">
      <button type="button" class="rule-color-picker-btn" data-action="toggle-color-dropdown" data-color="${selectedHex}" style="background:${selectedHex};" title="Pick color"></button>
      <div class="rule-color-picker-dropdown">${dots}</div>
    </div>`;
  }

  // ---- Sound preview ----
  let previewAudio = null;

  // ---- Inline edit row HTML ----
  function editRowHtml(id, threshold, lookback, color) {
    return `
    <tr class="rule-edit-row" data-editing-id="${id || ''}">
      <td>
        <div class="num-stepper num-stepper-sm">
          <button type="button" class="num-stepper-btn" data-action="step-down" data-target="inline-threshold">−</button>
          <input type="number" data-field="inline-threshold" min="0.3" max="100" step="0.1" value="${parseFloat(threshold).toFixed(1)}" class="num-stepper-input">
          <button type="button" class="num-stepper-btn" data-action="step-up" data-target="inline-threshold">+</button>
        </div>
      </td>
      <td>
        <div class="num-stepper num-stepper-sm">
          <button type="button" class="num-stepper-btn" data-action="step-down" data-target="inline-lookback">−</button>
          <input type="number" data-field="inline-lookback" min="1" max="60" step="1" value="${lookback}" class="num-stepper-input">
          <button type="button" class="num-stepper-btn" data-action="step-up" data-target="inline-lookback">+</button>
        </div>
      </td>
      <td>${colorPickerHtml(color)}</td>
      <td></td>
      <td class="rules-table-actions">
        <button type="button" data-action="save-inline-rule" class="btn btn-icon" title="Save"><i class="ri-check-line"></i></button>
        <button type="button" data-action="cancel-inline-rule" class="btn btn-icon" title="Cancel"><i class="ri-close-line"></i></button>
      </td>
    </tr>`;
  }

  // ---- Number stepper (custom +/- buttons) ----
  function stepValue(targetField, direction) {
    const input = $(`[data-field="${targetField}"]`);
    if (!input) return;
    const isFormatted = input.classList.contains("num-stepper-formatted");
    const step = parseFloat(input.dataset.step || input.step) || 1;
    const min = parseFloat(input.dataset.min ?? input.min);
    const max = parseFloat(input.dataset.max ?? input.max);
    let val = isFormatted ? parseFormatted(input.value) : (parseFloat(input.value) || 0);
    val += direction * step;
    if (!isNaN(min) && val < min) val = min;
    if (!isNaN(max) && val > max) val = max;
    val = Math.round(val * 100) / 100;
    const useFixed = targetField === "inline-threshold";
    input.value = isFormatted ? formatNumber(val) : useFixed ? val.toFixed(1) : val;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  // Format on blur, parse on focus for formatted inputs
  $$(".num-stepper-formatted").forEach((input) => {
    input.addEventListener("focus", () => {
      input.value = parseFormatted(input.value);
    });
    input.addEventListener("blur", () => {
      input.value = formatNumber(parseFormatted(input.value));
    });
  });

  // ---- Event delegation ----
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;

    const action = btn.getAttribute("data-action");
    const ruleId = btn.getAttribute("data-rule-id");

    switch (action) {
      case "step-up":
        stepValue(btn.getAttribute("data-target"), 1);
        break;
      case "step-down":
        stepValue(btn.getAttribute("data-target"), -1);
        break;
      case "add-rule":
        addInlineRow();
        break;
      case "edit-rule":
        editInlineRow(ruleId);
        break;
      case "delete-rule":
        deleteRule(ruleId);
        break;
      case "save-inline-rule":
        saveInlineRule();
        break;
      case "cancel-inline-rule":
        cancelInlineRow();
        break;
      case "toggle-color-dropdown":
        btn.nextElementSibling.classList.toggle("is-open");
        break;
      case "inline-pick-color": {
        const hex = btn.dataset.color;
        const picker = btn.closest(".rule-color-picker");
        const pickerBtn = picker.querySelector(".rule-color-picker-btn");
        pickerBtn.style.background = hex;
        pickerBtn.dataset.color = hex;
        picker.querySelector(".rule-color-picker-dropdown").classList.remove("is-open");
        break;
      }
      case "preview-notif-sound":
        previewNotifSound();
        break;
      case "add-watchlist":
        addTag("watchlist");
        break;
      case "add-blacklist":
        addTag("blacklist");
        break;
      case "remove-tag":
        removeTag(btn);
        break;
      case "reset-section":
        resetSection(btn.getAttribute("data-section"));
        break;
      case "reset-all":
        resetAll();
        break;
    }
  });

  // ---- Inline rule editing ----
  function cancelInlineRow() {
    const row = rulesTbody.querySelector('.rule-edit-row');
    if (!row) return;
    const id = row.dataset.editingId;
    // If editing existing rule, restore original row
    const orig = rulesTbody.querySelector(`tr[data-rule-id="${id}"][style*="display: none"]`);
    if (orig) orig.style.display = '';
    row.remove();
  }

  function addInlineRow() {
    cancelInlineRow();
    rulesTbody.insertAdjacentHTML('beforeend', editRowHtml('', 2, 2, '#10b981'));
    const row = rulesTbody.querySelector('.rule-edit-row');
    row.querySelector('[data-field="inline-threshold"]').focus();
  }

  function editInlineRow(ruleId) {
    cancelInlineRow();
    const origRow = rulesTbody.querySelector(`tr[data-rule-id="${ruleId}"]`);
    if (!origRow) return;
    // Read current values from the row
    api("GET", `/api/rules/${ruleId}`).then(data => {
      origRow.style.display = 'none';
      origRow.insertAdjacentHTML('afterend', editRowHtml(
        ruleId, data.threshold_pct, data.lookback_min, data.color || '#10b981'
      ));
      const row = rulesTbody.querySelector('.rule-edit-row');
      row.querySelector('[data-field="inline-threshold"]').focus();
    });
  }

  function saveInlineRule() {
    const row = rulesTbody.querySelector('.rule-edit-row');
    if (!row) return;
    const id = row.dataset.editingId;
    const threshold = parseFloat(row.querySelector('[data-field="inline-threshold"]').value);
    const lookback = parseInt(row.querySelector('[data-field="inline-lookback"]').value, 10);
    const colorBtn = row.querySelector('.rule-color-picker-btn');
    const color = colorBtn ? colorBtn.dataset.color : '#10b981';
    const name = `Pump ${threshold}%/${lookback}m`;
    const data = { name, threshold_pct: threshold, lookback_min: lookback, color, enabled: true };

    console.log('[settings] saving rule:', id ? `PUT #${id}` : 'POST new', data);

    const promise = id
      ? api("PUT", `/api/rules/${id}`, data)
      : api("POST", "/api/rules", data);

    promise
      .then(() => { sessionStorage.setItem("_toast", "Saved"); location.reload(); })
      .catch((err) => { console.error('[settings] save failed:', err); showModal(err.message); });
  }

  async function deleteRule(ruleId) {
    const ok = await showModal("Delete this rule?", { confirm: true, confirmLabel: "Delete", danger: true });
    if (!ok) return;
    api("DELETE", `/api/rules/${ruleId}`)
      .then(() => { sessionStorage.setItem("_toast", "Deleted"); location.reload(); })
      .catch((err) => showModal(err.message));
  }

  function previewNotifSound() {
    const sel = $('[data-field="notif-sound-file"]');
    if (!sel || !sel.value) return;
    if (previewAudio) {
      previewAudio.pause();
      previewAudio = null;
    }
    previewAudio = new Audio(`/api/sounds/${encodeURIComponent(sel.value)}`);
    previewAudio.play().catch(() => {});
  }

  // ---- Toast system ----
  const toastContainer = $('[data-el="toast-container"]');
  let toastTimer = null;

  // Show pending toast after page reload (rules save/delete)
  const pendingToast = sessionStorage.getItem("_toast");
  if (pendingToast) {
    sessionStorage.removeItem("_toast");
    setTimeout(() => showToast(pendingToast), 100);
  }

  function showToast(message, undoFn) {
    if (!toastContainer) return;
    clearTimeout(toastTimer);
    toastContainer.innerHTML = "";

    const el = document.createElement("div");
    el.className = "toast";

    let html = `<i class="ri-check-line toast-icon"></i>` +
      `<span class="toast-message">${message}</span>`;
    if (undoFn) {
      html += `<button data-action="toast-undo" class="toast-undo">Undo</button>`;
    }
    html += `<button data-action="toast-dismiss" class="toast-dismiss">` +
      `<i class="ri-close-line"></i></button>`;
    el.innerHTML = html;

    if (undoFn) {
      el.querySelector('[data-action="toast-undo"]')
        .addEventListener("click", () => {
          clearTimeout(toastTimer);
          undoFn();
          dismissToast(el);
        });
    }

    el.querySelector('[data-action="toast-dismiss"]')
      .addEventListener("click", () => {
        clearTimeout(toastTimer);
        dismissToast(el);
      });

    toastContainer.appendChild(el);
    toastTimer = setTimeout(() => dismissToast(el), 5000);
  }

  function dismissToast(el) {
    if (!el || !el.parentNode) return;
    el.classList.add("toast-exit");
    setTimeout(() => el.remove(), 300);
  }

  // ---- Notifications section ----
  const nSoundEnabled = $('[data-field="notif-sound-enabled"]');
  const nCooldown = $('[data-field="notif-cooldown"]');
  const nSoundFile = $('[data-field="notif-sound-file"]');
  const nDedupeHold = $('[data-field="notif-dedupe-hold"]');

  function getSoundValue() {
    if (!nSoundFile) return "pulse.wav";
    return nSoundFile.dataset.value || "pulse.wav";
  }

  function setSoundValue(val) {
    if (!nSoundFile) return;
    nSoundFile.dataset.value = val;
    const label = nSoundFile.querySelector('.custom-select-label');
    const name = val.replace(/\.(wav|mp3)$/, '');
    if (label) label.textContent = name.charAt(0).toUpperCase() + name.slice(1);
    nSoundFile.querySelectorAll('.custom-select-option').forEach(opt => {
      opt.classList.toggle('is-selected', opt.dataset.value === val);
    });
  }

  // Toggle dropdown
  document.addEventListener('click', (e) => {
    const toggleBtn = e.target.closest('[data-action="toggle-select"]');
    if (toggleBtn) {
      const dropdown = toggleBtn.nextElementSibling;
      dropdown.classList.toggle('is-open');
      return;
    }
    const opt = e.target.closest('.custom-select-option');
    if (opt) {
      const parent = opt.closest('.custom-select');
      opt.closest('.custom-select-dropdown').classList.remove('is-open');
      // Only handle sound picker here; timezone has its own handler
      if (parent && parent.dataset.field === 'notif-sound-file') {
        setSoundValue(opt.dataset.value);
        autoSave('notifications', saveNotifications);
      }
      return;
    }
    // Close any open dropdowns on outside click
    document.querySelectorAll('.custom-select-dropdown.is-open').forEach(d => d.classList.remove('is-open'));
  });

  function snapshotNotifications() {
    return {
      sound_enabled: nSoundEnabled.checked,
      alert_cooldown_seconds: parseInt(nCooldown.value, 10),
      alert_sound_file: getSoundValue(),
      dedupe_hold_minutes: nDedupeHold ? parseInt(nDedupeHold.value, 10) : undefined,
    };
  }

  function applyNotifications(data) {
    nSoundEnabled.checked = data.sound_enabled;
    nCooldown.value = data.alert_cooldown_seconds;
    if (data.alert_sound_file) setSoundValue(data.alert_sound_file);
    if (nDedupeHold && data.dedupe_hold_minutes != null) nDedupeHold.value = data.dedupe_hold_minutes;
  }

  if (nCooldown) {
    fetch("/api/settings/notifications")
      .then((r) => r.json())
      .then((data) => applyNotifications(data))
      .catch(() => {});
  }

  // Auto-save debounce helper
  let _autoSaveTimers = {};
  function autoSave(section, saveFn) {
    clearTimeout(_autoSaveTimers[section]);
    _autoSaveTimers[section] = setTimeout(saveFn, 400);
  }

  function saveNotifications() {
    if (!nSoundEnabled || !nCooldown) return;
    const body = snapshotNotifications();
    api("PUT", "/api/settings/notifications", body)
      .then(() => showToast("Saved"))
      .catch((err) => showModal(err.message));
  }

  // Auto-save on change
  [nSoundEnabled, nCooldown, nDedupeHold].forEach(el => {
    if (!el) return;
    const evt = el.type === 'checkbox' ? 'change' : 'input';
    el.addEventListener(evt, () => autoSave('notifications', saveNotifications));
  });

  // ---- Filters section ----
  const fVolume = $('[data-field="filter-volume"]');
  const fAge = $('[data-field="filter-age"]');
  const watchlistChips = $('[data-el="watchlist-chips"]');
  const blacklistChips = $('[data-el="blacklist-chips"]');
  const watchlistInput = $('[data-field="watchlist-input"]');
  const blacklistInput = $('[data-field="blacklist-input"]');

  let watchlistTags = [];
  let blacklistTags = [];

  function snapshotFilters() {
    return {
      min_volume_usd: parseFormatted(fVolume.value),
      min_age_days: parseInt(fAge.value, 10),
      watchlist: [...watchlistTags],
      blacklist: [...blacklistTags],
    };
  }

  function applyFilters(data) {
    fVolume.value = formatNumber(data.min_volume_usd);
    fAge.value = data.min_age_days;
    watchlistTags = data.watchlist || [];
    blacklistTags = data.blacklist || [];
    renderChips(watchlistChips, watchlistTags, "watchlist");
    renderChips(blacklistChips, blacklistTags, "blacklist");
  }

  function renderChips(container, tags, listName) {
    if (!container) return;
    container.innerHTML = tags
      .map(
        (tag) =>
          `<span class="chip">${tag}<button type="button" data-action="remove-tag" data-list="${listName}" data-tag="${tag}" class="chip-remove" title="Remove"><i class="ri-close-line"></i></button></span>`
      )
      .join("");
  }

  function showErrorToast(message) {
    if (!toastContainer) return;
    clearTimeout(toastTimer);
    toastContainer.innerHTML = "";
    const el = document.createElement("div");
    el.className = "toast is-error";
    el.innerHTML =
      `<i class="ri-error-warning-line toast-icon"></i>` +
      `<span class="toast-message">${message}</span>` +
      `<button data-action="toast-dismiss" class="toast-dismiss"><i class="ri-close-line"></i></button>`;
    el.querySelector('[data-action="toast-dismiss"]')
      .addEventListener("click", () => { clearTimeout(toastTimer); dismissToast(el); });
    toastContainer.appendChild(el);
    toastTimer = setTimeout(() => dismissToast(el), 3000);
  }

  // ---- Autocomplete dropdown ----
  const watchlistDropdown = $('[data-el="watchlist-dropdown"]');
  const blacklistDropdown = $('[data-el="blacklist-dropdown"]');
  let highlightIdx = -1;

  function showDropdown(input, dropdown, listName) {
    if (!dropdown) return;
    const raw = input.value.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
    if (!raw || knownSymbols.length === 0) {
      dropdown.classList.remove("is-open");
      return;
    }
    const tags = listName === "watchlist" ? watchlistTags : blacklistTags;
    const matches = knownSymbols
      .filter((s) => s.includes(raw) && !tags.includes(s))
      .slice(0, 8);
    if (matches.length === 0) {
      dropdown.classList.remove("is-open");
      return;
    }
    highlightIdx = -1;
    dropdown.innerHTML = matches
      .map((s) => `<button type="button" class="tag-dropdown-item" data-symbol="${s}">${s}</button>`)
      .join("");
    dropdown.classList.add("is-open");
  }

  function hideDropdown(dropdown) {
    if (dropdown) {
      dropdown.classList.remove("is-open");
      highlightIdx = -1;
    }
  }

  function pickSymbol(symbol, listName) {
    const tags = listName === "watchlist" ? watchlistTags : blacklistTags;
    const container = listName === "watchlist" ? watchlistChips : blacklistChips;
    const input = listName === "watchlist" ? watchlistInput : blacklistInput;
    const dropdown = listName === "watchlist" ? watchlistDropdown : blacklistDropdown;
    if (tags.includes(symbol)) {
      showErrorToast(symbol + " already added");
      return;
    }
    tags.push(symbol);
    renderChips(container, tags, listName);
    if (input) { input.value = ""; input.focus(); }
    hideDropdown(dropdown);
    autoSave('filters', saveFilters);
  }

  function addTag(listName) {
    const input = listName === "watchlist" ? watchlistInput : blacklistInput;
    const tags = listName === "watchlist" ? watchlistTags : blacklistTags;
    const container = listName === "watchlist" ? watchlistChips : blacklistChips;
    const dropdown = listName === "watchlist" ? watchlistDropdown : blacklistDropdown;
    if (!input) return;

    const raw = input.value.trim();
    const val = raw.toUpperCase().replace(/[^A-Z0-9]/g, "");

    if (!val) {
      if (raw.length > 0) showErrorToast("Only letters and numbers allowed");
      input.value = "";
      return;
    }
    if (tags.includes(val)) {
      showErrorToast(val + " already added");
      input.value = "";
      return;
    }
    if (tags.length >= 100) {
      showErrorToast("Maximum 100 symbols");
      return;
    }
    if (knownSet.size > 0 && !knownSet.has(val)) {
      showErrorToast(val + " is not a valid trading pair");
      return;
    }
    tags.push(val);
    renderChips(container, tags, listName);
    input.value = "";
    input.focus();
    hideDropdown(dropdown);
    autoSave('filters', saveFilters);
  }

  function removeTag(btn) {
    const listName = btn.getAttribute("data-list");
    const tag = btn.getAttribute("data-tag");
    const tags = listName === "watchlist" ? watchlistTags : blacklistTags;
    const container = listName === "watchlist" ? watchlistChips : blacklistChips;
    const idx = tags.indexOf(tag);
    if (idx !== -1) tags.splice(idx, 1);
    renderChips(container, tags, listName);
    autoSave('filters', saveFilters);
  }

  if (fVolume) {
    [watchlistInput, blacklistInput].forEach((input) => {
      if (!input) return;
      const listName = input === watchlistInput ? "watchlist" : "blacklist";
      const dropdown = input === watchlistInput ? watchlistDropdown : blacklistDropdown;
      input.addEventListener("keydown", (e) => {
        const items = dropdown ? dropdown.querySelectorAll(".tag-dropdown-item") : [];
        if (e.key === "ArrowDown" && items.length) {
          e.preventDefault();
          highlightIdx = Math.min(highlightIdx + 1, items.length - 1);
          items.forEach((el, i) => el.classList.toggle("is-highlighted", i === highlightIdx));
          items[highlightIdx].scrollIntoView({ block: "nearest" });
        } else if (e.key === "ArrowUp" && items.length) {
          e.preventDefault();
          highlightIdx = Math.max(highlightIdx - 1, 0);
          items.forEach((el, i) => el.classList.toggle("is-highlighted", i === highlightIdx));
          items[highlightIdx].scrollIntoView({ block: "nearest" });
        } else if (e.key === "Enter") {
          e.preventDefault();
          if (highlightIdx >= 0 && items[highlightIdx]) {
            // User navigated with arrows — pick highlighted item
            pickSymbol(items[highlightIdx].dataset.symbol, listName);
          } else if (items.length === 1) {
            // Exactly one match — pick it automatically
            pickSymbol(items[0].dataset.symbol, listName);
          } else if (items.length > 1) {
            // Multiple matches, none highlighted — pick first
            pickSymbol(items[0].dataset.symbol, listName);
          } else {
            // No dropdown matches — try raw text (uppercased)
            addTag(listName);
          }
        } else if (e.key === "Escape") {
          hideDropdown(dropdown);
        }
      });
      input.addEventListener("input", () => showDropdown(input, dropdown, listName));
      input.addEventListener("blur", () => setTimeout(() => hideDropdown(dropdown), 200));
      if (dropdown) {
        dropdown.addEventListener("click", (e) => {
          const item = e.target.closest(".tag-dropdown-item");
          if (item) pickSymbol(item.dataset.symbol, listName);
        });
      }
    });

    fetch("/api/settings/filters")
      .then((r) => r.json())
      .then((data) => applyFilters(data))
      .catch(() => {});

    // Auto-save on volume/age change
    [fVolume, fAge].forEach(el => {
      if (!el) return;
      el.addEventListener('input', () => autoSave('filters', saveFilters));
    });
  }

  function saveFilters() {
    if (!fVolume || !fAge) return;
    const body = snapshotFilters();
    api("PUT", "/api/settings/filters", body)
      .then(() => showToast("Saved"))
      .catch((err) => showModal(err.message));
  }

  // ---- Display section ----
  const dTimezone = $('[data-field="display-timezone"]');
  const dRows = $('[data-field="display-rows"]');
  const dCoinglass = $('[data-field="display-coinglass"]');
  const dTradingview = $('[data-field="display-tradingview"]');

  function getTimezoneValue() {
    if (!dTimezone) return "UTC";
    return dTimezone.dataset.value || "UTC";
  }

  function setTimezoneValue(val) {
    if (!dTimezone) return;
    dTimezone.dataset.value = val;
    const label = dTimezone.querySelector('.custom-select-label');
    if (label) label.textContent = val;
    dTimezone.querySelectorAll('.custom-select-option').forEach(opt => {
      opt.classList.toggle('is-selected', opt.dataset.value === val);
    });
  }

  // Handle timezone dropdown option click
  if (dTimezone) {
    dTimezone.addEventListener('click', (e) => {
      const opt = e.target.closest('.custom-select-option');
      if (opt) {
        setTimezoneValue(opt.dataset.value);
        opt.closest('.custom-select-dropdown').classList.remove('is-open');
        autoSave('display', saveDisplay);
      }
    });
  }

  function snapshotDisplay() {
    return {
      timezone: getTimezoneValue(),
      rows_per_page: parseInt(dRows.value, 10),
      show_coinglass: dCoinglass ? dCoinglass.checked : true,
      show_tradingview: dTradingview ? dTradingview.checked : true,
    };
  }

  function applyDisplay(data) {
    if (dTimezone) setTimezoneValue(data.timezone);
    if (dRows) dRows.value = data.rows_per_page;
    if (dCoinglass) dCoinglass.checked = data.show_coinglass !== false;
    if (dTradingview) dTradingview.checked = data.show_tradingview !== false;
  }

  if (dRows) {
    fetch("/api/settings/display")
      .then((r) => r.json())
      .then((data) => applyDisplay(data))
      .catch(() => {});
  }

  function saveDisplay() {
    if (!dTimezone || !dRows) return;
    const body = snapshotDisplay();
    api("PUT", "/api/settings/display", body)
      .then(() => showToast("Saved"))
      .catch((err) => showModal(err.message));
  }

  // Auto-save on display change
  [dRows].forEach(el => {
    if (!el) return;
    el.addEventListener('input', () => autoSave('display', saveDisplay));
  });
  [dCoinglass, dTradingview].forEach(el => {
    if (!el) return;
    el.addEventListener('change', () => autoSave('display', saveDisplay));
  });

  // ---- Reset ----
  const _sectionLabels = {
    rules: "Detection Rules",
    notifications: "Notifications",
    filters: "Filters",
    display: "Display",
  };

  async function resetSection(section) {
    const label = _sectionLabels[section] || section;
    const ok = await showModal(`Reset ${label} to defaults?`, { confirm: true, confirmLabel: "Reset", danger: true });
    if (!ok) return;
    api("POST", `/api/settings/reset/${section}`)
      .then(() => { sessionStorage.setItem("_toast", "Reset to defaults"); location.reload(); })
      .catch((err) => showModal(err.message));
  }

  async function resetAll() {
    const ok = await showModal("Reset ALL settings and rules to factory defaults?", { confirm: true, confirmLabel: "Reset All", danger: true });
    if (!ok) return;
    api("POST", "/api/settings/reset")
      .then(() => { sessionStorage.setItem("_toast", "Reset to defaults"); location.reload(); })
      .catch((err) => showModal(err.message));
  }

  // Close color dropdowns on click outside
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".rule-color-picker")) {
      $$(".rule-color-picker-dropdown.is-open").forEach(d => d.classList.remove("is-open"));
    }
  });

  // ---- Rule toggle (enable/disable from table) ----
  document.addEventListener("change", (e) => {
    const toggle = e.target.closest('[data-action="toggle-rule"]');
    if (!toggle) return;
    const ruleId = toggle.getAttribute("data-rule-id");
    api("PATCH", `/api/rules/${ruleId}`, { enabled: toggle.checked })
      .catch(() => { toggle.checked = !toggle.checked; });
  });

  // ---- Sidebar tab switching ----
  const sidebarLinks = $$(".settings-sidebar-link");
  const panels = $$("[data-section-panel]");

  function switchTab(name) {
    sidebarLinks.forEach((link) => {
      link.classList.toggle("is-active", link.getAttribute("data-nav") === name);
    });
    panels.forEach((panel) => {
      const id = panel.getAttribute("data-section-panel");
      if (id === "upgrade") {
        panel.classList.toggle("is-hidden", name === "reset");
      } else {
        panel.classList.toggle("is-hidden", id !== name);
      }
    });
  }

  sidebarLinks.forEach((link) => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      switchTab(link.getAttribute("data-nav"));
    });
  });
})();

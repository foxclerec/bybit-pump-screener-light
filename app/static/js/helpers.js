// helpers.js — shared utilities for all JS modules
"use strict";

const $ = (sel, root) => (root || document).querySelector(sel);
const $$ = (sel, root) => [...(root || document).querySelectorAll(sel)];

function csrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute("content") : "";
}

function api(method, url, body) {
  const opts = {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
    },
  };
  if (body) opts.body = JSON.stringify(body);
  return fetch(url, opts).then(async (r) => {
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || "Request failed");
    return data;
  });
}

function formatNumber(n) {
  return n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

function parseFormatted(str) {
  return parseFloat(String(str).replace(/,/g, "")) || 0;
}

// ---- Modal dialog (replaces native alert/confirm) ----
function showModal(message, { confirm = false, confirmLabel = "Confirm", cancelLabel = "Cancel", danger = false } = {}) {
  return new Promise((resolve) => {
    // Remove existing modal
    const old = document.getElementById("app-modal-overlay");
    if (old) old.remove();

    const overlay = document.createElement("div");
    overlay.id = "app-modal-overlay";
    overlay.className = "modal-overlay";

    const btnClass = danger ? "btn btn-outline-danger" : "btn btn-primary";
    const buttons = confirm
      ? `<button data-modal="cancel" class="btn btn-ghost">${cancelLabel}</button>
         <button data-modal="ok" class="${btnClass}">${confirmLabel}</button>`
      : `<button data-modal="ok" class="btn btn-primary">OK</button>`;

    overlay.innerHTML = `
      <div class="modal-card">
        <p class="modal-message">${message}</p>
        <div class="modal-actions">${buttons}</div>
      </div>`;

    document.body.appendChild(overlay);
    // Focus first action button
    overlay.querySelector("[data-modal]").focus();

    function close(result) {
      overlay.classList.add("modal-out");
      setTimeout(() => overlay.remove(), 150);
      resolve(result);
    }

    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close(false);
      const action = e.target.closest("[data-modal]");
      if (!action) return;
      close(action.dataset.modal === "ok");
    });

    overlay.addEventListener("keydown", (e) => {
      if (e.key === "Escape") close(false);
    });
  });
}

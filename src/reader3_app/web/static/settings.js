function $(id) {
  return document.getElementById(id);
}

function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

async function jsonFetch(url, opts = {}) {
  const resp = await fetch(url, opts);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const msg = data?.detail || data?.message || `${resp.status} ${resp.statusText}`;
    throw new Error(msg);
  }
  return data;
}

const DB_NAME = "reader3_ai_assistant";
const DB_VERSION = 1;
const STORE_CONVERSATIONS = "conversations";
const STORE_SUMMARIES = "summaries";

function openDb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onerror = () => reject(req.error);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_CONVERSATIONS)) {
        const store = db.createObjectStore(STORE_CONVERSATIONS, { keyPath: "id" });
        store.createIndex("book_uuid", "book_uuid", { unique: false });
        store.createIndex("book_uuid_provider", ["book_uuid", "provider"], { unique: false });
      }
      if (!db.objectStoreNames.contains(STORE_SUMMARIES)) {
        const store = db.createObjectStore(STORE_SUMMARIES, { keyPath: "cache_key" });
        store.createIndex("book_uuid", "book_uuid", { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
  });
}

async function clearStore(storeName) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, "readwrite");
    const store = tx.objectStore(storeName);
    const req = store.clear();
    req.onerror = () => reject(req.error);
    req.onsuccess = () => resolve();
  });
}

function setStatus(el, text) {
  if (!el) return;
  el.textContent = text || "";
}

function providerRequiresKey(name) {
  return ["anthropic", "openai", "gemini", "openrouter"].includes(String(name || "").toLowerCase());
}

function renderProviderCard(p, ollamaStatus, ollamaModels) {
  const name = String(p.name || "");
  const enabled = Boolean(p.enabled);
  const apiKeyConfigured = Boolean(p.api_key_configured);
  const baseUrl = String(p.base_url || "");
  const modelName = String(p.model_name || "");
  const timeout = Number(p.timeout || 30);
  const maxRetries = Number(p.max_retries ?? 0);

  const statusPill =
    name === "ollama"
      ? ollamaStatus?.running
        ? `<span class="pill ok">✅ Running</span>`
        : `<span class="pill bad">⚠️ Not connected</span>`
      : enabled
        ? `<span class="pill ok">Enabled</span>`
        : `<span class="pill">Disabled</span>`;

  const modelsHint =
    name === "ollama" && Array.isArray(ollamaModels?.models)
      ? `(${ollamaModels.models.length} local models)`
      : "";

  const keyRow = providerRequiresKey(name)
    ? `
      <label class="label">
        API key ${apiKeyConfigured ? '<span class="pill ok">Configured</span>' : '<span class="pill bad">Missing</span>'}
        <input type="password" data-k="api_key" placeholder="Paste API key to set/update (leave blank to keep)" />
      </label>
    `
    : `
      <div class="label">
        API key
        <div class="hint">No API key required.</div>
      </div>
    `;

  return `
    <div class="provider-card" data-provider="${escapeHtml(name)}">
      <div class="provider-head">
        <div class="provider-name">${escapeHtml(name)} ${statusPill} <span class="hint">${escapeHtml(modelsHint)}</span></div>
        <label class="checkbox">
          <input type="checkbox" data-k="enabled" ${enabled ? "checked" : ""} />
          Enabled
        </label>
      </div>
      <div class="provider-grid">
        <label class="label">
          Base URL
          <input type="text" data-k="base_url" value="${escapeHtml(baseUrl)}" />
        </label>
        <label class="label">
          Model
          <input type="text" data-k="model_name" value="${escapeHtml(modelName)}" />
        </label>
        <label class="label">
          Timeout (seconds)
          <input type="number" data-k="timeout" min="5" max="120" value="${escapeHtml(timeout)}" />
        </label>
        <label class="label">
          Max retries
          <input type="number" data-k="max_retries" min="0" max="10" value="${escapeHtml(maxRetries)}" />
        </label>
        ${keyRow}
      </div>
      <div class="row">
        <button class="btn" data-action="save">Save</button>
        <button class="btn" data-action="test">Test</button>
        ${name === "ollama" ? `<button class="btn" data-action="refresh-models">Refresh models</button>` : ""}
        <span class="status" data-role="status"></span>
      </div>
      ${
        name === "ollama" && !ollamaStatus?.running
          ? `<div class="hint">Install: <code>brew install ollama</code>. Start: <code>ollama serve</code>. Pull a model: <code>ollama pull qwen3:8b</code>.</div>`
          : ""
      }
    </div>
  `;
}

async function loadAll() {
  const [settings, providersMeta] = await Promise.all([jsonFetch("/api/settings"), jsonFetch("/api/settings/providers")]);
  let ollamaStatus = null;
  let ollamaModels = null;
  try {
    ollamaStatus = await jsonFetch("/api/ollama/status");
  } catch {
    ollamaStatus = { running: false };
  }
  try {
    ollamaModels = await jsonFetch("/api/ollama/models");
  } catch {
    ollamaModels = { models: [] };
  }
  return { settings, providersMeta, ollamaStatus, ollamaModels };
}

function fillPreferencesUI(settings) {
  const prefs = settings?.preferences || {};
  $("settings-streaming-enabled").checked = Boolean(prefs.streaming_enabled ?? true);
  $("settings-show-timestamps").checked = Boolean(prefs.show_timestamps ?? true);
  $("settings-auto-suggest").checked = Boolean(prefs.auto_suggest_questions ?? true);
}

function fillDefaultProviderUI(settings, providersMeta) {
  const sel = $("settings-default-provider");
  sel.innerHTML = "";
  const available = Array.isArray(providersMeta?.providers) ? providersMeta.providers : [];
  available.forEach((p) => {
    const opt = document.createElement("option");
    opt.value = String(p.name || "");
    opt.textContent = String(p.display_name || p.name || "");
    sel.appendChild(opt);
  });
  sel.value = String(settings?.default_provider || "anthropic");
}

function renderProviders(settings, ollamaStatus, ollamaModels) {
  const root = $("settings-providers");
  root.innerHTML = "";
  const providers = Array.isArray(settings?.providers) ? settings.providers : [];
  root.innerHTML = providers.map((p) => renderProviderCard(p, ollamaStatus, ollamaModels)).join("");
}

function getProviderPatch(cardEl) {
  const patch = {};
  const enabledEl = cardEl.querySelector('input[data-k="enabled"]');
  if (enabledEl) patch.enabled = Boolean(enabledEl.checked);
  const inputs = Array.from(cardEl.querySelectorAll("input[data-k]"));
  inputs.forEach((el) => {
    const k = el.getAttribute("data-k");
    if (!k || k === "enabled") return;
    if (k === "api_key") {
      const v = String(el.value || "");
      if (v.trim()) patch.api_key = v.trim();
      return;
    }
    if (k === "timeout" || k === "max_retries") {
      patch[k] = Number(el.value || 0);
      return;
    }
    patch[k] = String(el.value || "");
  });
  return patch;
}

function installProviderHandlers() {
  const root = $("settings-providers");
  root.addEventListener("click", async (e) => {
    const btn = e.target?.closest?.("button[data-action]");
    if (!btn) return;
    const action = btn.getAttribute("data-action");
    const card = btn.closest(".provider-card");
    if (!card) return;
    const provider = card.getAttribute("data-provider");
    const statusEl = card.querySelector('[data-role="status"]');

    try {
      setStatus(statusEl, "");
      if (action === "save") {
        btn.disabled = true;
        const patch = getProviderPatch(card);
        await jsonFetch(`/api/settings/providers/${encodeURIComponent(provider)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(patch),
        });
        setStatus(statusEl, "Saved.");
      } else if (action === "test") {
        btn.disabled = true;
        const patch = getProviderPatch(card);
        const body = {};
        if (patch.api_key) body.api_key = patch.api_key;
        if (patch.base_url) body.base_url = patch.base_url;
        if (patch.model_name) body.model_name = patch.model_name;
        const res = await jsonFetch(`/api/settings/providers/${encodeURIComponent(provider)}/test`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        setStatus(statusEl, res.success ? `OK (${res.details?.latency_ms ?? "?"}ms)` : `Failed: ${res.message}`);
      } else if (action === "refresh-models") {
        btn.disabled = true;
        await jsonFetch("/api/ollama/models");
        setStatus(statusEl, "Refreshed. Reload page to see updated count.");
      }
    } catch (err) {
      setStatus(statusEl, `Error: ${err?.message || String(err)}`);
    } finally {
      btn.disabled = false;
    }
  });
}

function installPreferenceHandlers() {
  const btn = $("settings-save-preferences");
  const statusEl = $("settings-pref-status");
  btn.addEventListener("click", async () => {
    try {
      btn.disabled = true;
      setStatus(statusEl, "");
      const defaultProvider = $("settings-default-provider").value;
      const preferences = {
        streaming_enabled: $("settings-streaming-enabled").checked,
        show_timestamps: $("settings-show-timestamps").checked,
        auto_suggest_questions: $("settings-auto-suggest").checked,
      };
      await jsonFetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ default_provider: defaultProvider, preferences }),
      });
      setStatus(statusEl, "Saved.");
    } catch (err) {
      setStatus(statusEl, `Error: ${err?.message || String(err)}`);
    } finally {
      btn.disabled = false;
    }
  });
}

function installDataHandlers() {
  const convBtn = $("settings-clear-conversations");
  const sumBtn = $("settings-clear-summaries");
  const statusEl = $("settings-data-status");

  convBtn.addEventListener("click", async () => {
    if (!confirm("Clear ALL conversations in this browser?")) return;
    try {
      convBtn.disabled = true;
      setStatus(statusEl, "");
      await clearStore(STORE_CONVERSATIONS);
      setStatus(statusEl, "Conversations cleared.");
    } catch (err) {
      setStatus(statusEl, `Error: ${err?.message || String(err)}`);
    } finally {
      convBtn.disabled = false;
    }
  });

  sumBtn.addEventListener("click", async () => {
    if (!confirm("Clear ALL summaries in this browser?")) return;
    try {
      sumBtn.disabled = true;
      setStatus(statusEl, "");
      await clearStore(STORE_SUMMARIES);
      setStatus(statusEl, "Summaries cleared.");
    } catch (err) {
      setStatus(statusEl, `Error: ${err?.message || String(err)}`);
    } finally {
      sumBtn.disabled = false;
    }
  });
}

async function main() {
  try {
    const { settings, providersMeta, ollamaStatus, ollamaModels } = await loadAll();
    fillDefaultProviderUI(settings, providersMeta);
    fillPreferencesUI(settings);
    renderProviders(settings, ollamaStatus, ollamaModels);
    installProviderHandlers();
    installPreferenceHandlers();
    installDataHandlers();
  } catch (err) {
    const root = $("settings-providers");
    root.innerHTML = `<div class="status">Error loading settings: ${escapeHtml(err?.message || String(err))}</div>`;
  }
}

main();

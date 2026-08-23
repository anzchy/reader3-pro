// 0.4（007）：包成 IIFE，顶层符号不再挂到 window 上。
// 此前这四个文件各自定义一份 escapeHtml，同一页里谁后加载谁赢——reader.html
// 同时加载 search.js 与 ai.js，两份实现对 null/undefined 的处理并不相同。
// 无导出：四个文件都自初始化，实测无任何跨文件符号引用。
// 函数体不整体缩进，是为了不让这次的两行包裹淹没在 1900 行 whitespace diff 里。
(() => {
function escapeHtml(str) {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function nowIso() {
  return new Date().toISOString();
}

function downloadText(filename, text, mime = "text/plain") {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function parseSseBlock(block) {
  const lines = String(block || "").split(/\r?\n/);
  let event = "message";
  let data = "";
  for (const line of lines) {
    if (line.startsWith("event:")) event = line.slice("event:".length).trim() || "message";
    if (line.startsWith("data:")) data += line.slice("data:".length).trim();
  }
  if (!data) return null;
  try {
    return { event, data: JSON.parse(data) };
  } catch {
    return { event, data };
  }
}

async function* streamSseResponse(resp) {
  const reader = resp.body?.getReader?.();
  if (!reader) return;
  const decoder = new TextDecoder("utf-8");
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    while (true) {
      const idx = buf.indexOf("\n\n");
      if (idx < 0) break;
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const evt = parseSseBlock(block);
      if (evt) yield evt;
    }
  }
  const tail = buf.trim();
  if (tail) {
    const evt = parseSseBlock(tail);
    if (evt) yield evt;
  }
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

async function txGetAllByIndex(db, storeName, indexName, key) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, "readonly");
    const store = tx.objectStore(storeName);
    const index = store.index(indexName);
    const req = index.getAll(key);
    req.onerror = () => reject(req.error);
    req.onsuccess = () => resolve(req.result || []);
  });
}

async function txPut(db, storeName, value) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, "readwrite");
    const store = tx.objectStore(storeName);
    const req = store.put(value);
    req.onerror = () => reject(req.error);
    req.onsuccess = () => resolve(req.result);
  });
}

async function txDelete(db, storeName, key) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, "readwrite");
    const store = tx.objectStore(storeName);
    const req = store.delete(key);
    req.onerror = () => reject(req.error);
    req.onsuccess = () => resolve();
  });
}

async function txGet(db, storeName, key) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, "readonly");
    const store = tx.objectStore(storeName);
    const req = store.get(key);
    req.onerror = () => reject(req.error);
    req.onsuccess = () => resolve(req.result || null);
  });
}

function modelStorageKey(bookUuid, provider) {
  return `reader3.ai.model.${bookUuid}.${provider}`;
}

function activeConversationStorageKey(bookUuid, provider) {
  return `reader3.ai.activeConversation.${bookUuid}.${provider}`;
}

function getCtx() {
  const ctx = window.Reader3Ctx || {};
  return {
    bookId: ctx.bookId,
    bookUuid: ctx.bookUuid,
    provider: ctx.provider || "anthropic",
  };
}

class ReaderAIUI {
  constructor(ctx) {
    this.ctx = ctx;
    this.toggleBtn = document.getElementById("reader-ai-toggle");
    this.panel = document.getElementById("reader-ai-panel");
    this.closeBtn = document.getElementById("reader-ai-close");
    this.clearBtn = document.getElementById("reader-ai-clear");
    this.newChatBtn = document.getElementById("reader-ai-new-chat");
    this.exportBtn = document.getElementById("reader-ai-export");
    this.exportFmtEl = document.getElementById("reader-ai-export-format");
    this.providerEl = document.getElementById("reader-ai-provider");
    this.threadsEl = document.getElementById("reader-ai-threads");
    this.messagesEl = document.getElementById("reader-ai-messages");
    this.inputEl = document.getElementById("reader-ai-input");
    this.sendBtn = document.getElementById("reader-ai-send");
    this.stopBtn = document.getElementById("reader-ai-stop");
    this.quickBtns = Array.from(document.querySelectorAll("[data-ai-summary-type]"));

    this.db = null;
    this.conversation = null;
    this.currentModel = localStorage.getItem(modelStorageKey(ctx.bookUuid, ctx.provider)) || "";
    this.isBusy = false;
    this.streamingEnabled = true;
    this.abortController = null;
    this.msgElById = new Map();
    this.diskSyncTimer = null;

    this.toggleBtn?.addEventListener("click", () => this.toggle());
    this.closeBtn?.addEventListener("click", () => this.close());
    this.clearBtn?.addEventListener("click", () => this.clearConversation());
    this.newChatBtn?.addEventListener("click", () => this.newChat());
    this.exportBtn?.addEventListener("click", () => this.exportConversation());

    this.quickBtns.forEach((btn) => {
      btn.addEventListener("click", () => this.runSummary(btn.getAttribute("data-ai-summary-type")));
    });

    this.sendBtn?.addEventListener("click", () => this.sendQuestion());
    this.stopBtn?.addEventListener("click", () => this.abort());
    this.inputEl?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.sendQuestion();
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this.panel?.classList.contains("is-open")) this.close();
    });

    window.Reader3AIAskEnabled = true;
    window.addEventListener("reader3:ai:ask", (evt) => {
      const detail = evt?.detail || {};
      const quote = String(detail.quote || "").trim();
      const context = String(detail.context || "").trim();
      if (!quote) return;
      this.handleAskEvent(quote, context).catch(() => {});
    });

    const refreshIfOpen = async () => {
      if (this.isBusy) return;
      if (!this.panel?.classList.contains("is-open")) return;
      const changed = await this.loadPreferences();
      if (changed) await this.restoreConversation();
    };

    window.addEventListener("focus", () => {
      refreshIfOpen().catch(() => {});
    });
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") refreshIfOpen().catch(() => {});
    });
  }

  async ensureDb() {
    if (this.db) return this.db;
    this.db = await openDb();
    return this.db;
  }

  setBusy(busy) {
    this.isBusy = !!busy;
    if (this.sendBtn) this.sendBtn.disabled = busy;
    if (this.inputEl) this.inputEl.disabled = busy;
    if (this.stopBtn) this.stopBtn.style.display = busy && this.abortController ? "inline-flex" : "none";
  }

  setProvider(provider, model) {
    const label = model ? `${provider} · ${model}` : provider;
    if (this.providerEl) this.providerEl.textContent = label;
  }

  open() {
    this.panel?.classList.add("is-open");
    this.panel?.setAttribute("aria-hidden", "false");
  }

  close() {
    this.panel?.classList.remove("is-open");
    this.panel?.setAttribute("aria-hidden", "true");
  }

  async toggle() {
    const isOpen = this.panel?.classList.contains("is-open");
    if (isOpen) {
      this.close();
      return;
    }
    this.open();
    await this.loadPreferences();
    await this.restoreConversation();
  }

  async loadPreferences() {
    try {
      const prevProvider = String(this.ctx.provider || "");
      const prevModel = String(this.currentModel || "");
      const resp = await fetch("/api/settings");
      const data = await resp.json().catch(() => ({}));
      const prefs = data?.preferences || {};
      this.streamingEnabled = !!prefs.streaming_enabled;

      const nextProvider = String(data?.default_provider || this.ctx.provider || "anthropic").trim().toLowerCase();
      if (nextProvider) {
        this.ctx.provider = nextProvider;
      }

      const providers = Array.isArray(data?.providers) ? data.providers : [];
      const pCfg = providers.find((p) => String(p?.name || "").trim().toLowerCase() === this.ctx.provider) || null;
      const settingsModel = String(pCfg?.model_name || "").trim();
      if (settingsModel) {
        this.currentModel = settingsModel;
        localStorage.setItem(modelStorageKey(this.ctx.bookUuid, this.ctx.provider), settingsModel);
      } else {
        this.currentModel = localStorage.getItem(modelStorageKey(this.ctx.bookUuid, this.ctx.provider)) || this.currentModel || "";
      }

      this.setProvider(this.ctx.provider, this.currentModel);
      return prevProvider !== String(this.ctx.provider || "") || prevModel !== String(this.currentModel || "");
    } catch {
      this.streamingEnabled = true;
      return false;
    }
  }

  abort() {
    try {
      this.abortController?.abort?.();
    } catch {
      // ignore
    }
  }

  async restoreConversation() {
    const db = await this.ensureDb();
    const list = await txGetAllByIndex(db, STORE_CONVERSATIONS, "book_uuid_provider", [this.ctx.bookUuid, this.ctx.provider]);
    list.sort((a, b) => String(b.last_updated || "").localeCompare(String(a.last_updated || "")));

    const activeId = localStorage.getItem(activeConversationStorageKey(this.ctx.bookUuid, this.ctx.provider)) || "";
    const active = activeId ? list.find((c) => String(c?.id || "") === activeId) : null;
    this.conversation = active || list[0] || null;

    // If this browser has no cached conversations, try to load the most recent one from disk.
    if (!this.conversation) {
      try {
        const resp = await fetch(`/api/ai/conversations/${encodeURIComponent(this.ctx.bookUuid)}?provider=${encodeURIComponent(this.ctx.provider)}`);
        const data = await resp.json().catch(() => ({}));
        const threads = Array.isArray(data?.conversations) ? data.conversations : [];
        const cid = String(threads?.[0]?.conversation_id || "");
        if (cid) {
          const tResp = await fetch(`/api/ai/conversations/${encodeURIComponent(this.ctx.bookUuid)}/${encodeURIComponent(cid)}`);
          const tData = await tResp.json().catch(() => ({}));
          if (tResp.ok && tData?.conversation_id) {
            const conv = {
              id: String(tData.conversation_id),
              book_uuid: this.ctx.bookUuid,
              provider: this.ctx.provider,
              created_at: String(tData.created_at || nowIso()),
              last_updated: String(tData.last_updated || nowIso()),
              model: String(tData.model || ""),
              messages: Array.isArray(tData.messages)
                ? tData.messages.map((m) => ({
                    id: String(m.id || crypto.randomUUID()),
                    conversation_id: String(tData.conversation_id),
                    role: m.role,
                    content: m.content,
                    timestamp: m.timestamp,
                    metadata: m.metadata || {},
                  }))
                : [],
            };
            this.conversation = conv;
            await txPut(db, STORE_CONVERSATIONS, conv);
          }
        }
      } catch {
        // ignore
      }
    }

    if (!this.conversation) {
      await this.newChat();
    } else {
      localStorage.setItem(activeConversationStorageKey(this.ctx.bookUuid, this.ctx.provider), String(this.conversation.id || ""));
    }

    await this.renderThreads();
    this.renderAll();
    this.setProvider(this.ctx.provider, this.currentModel);
  }

  async renderThreads() {
    if (!this.threadsEl) return;
    const db = await this.ensureDb();
    const list = await txGetAllByIndex(db, STORE_CONVERSATIONS, "book_uuid_provider", [this.ctx.bookUuid, this.ctx.provider]);
    list.sort((a, b) => String(b.last_updated || "").localeCompare(String(a.last_updated || "")));
    this.threadsEl.innerHTML = "";
    list.forEach((c) => {
      const div = document.createElement("div");
      div.className = "ai-thread";
      if (this.conversation && String(c.id) === String(this.conversation.id)) div.classList.add("is-active");
      const title = this._threadTitle(c);
      const meta = `${new Date(String(c.last_updated || "") || Date.now()).toLocaleString()} · ${(c.messages || []).length} msgs`;
      div.innerHTML = `<div>${escapeHtml(title || "(empty)")}</div><div class="meta">${escapeHtml(meta)}</div>`;
      div.addEventListener("click", async () => {
        if (this.isBusy) return;
        await this.switchConversation(String(c.id || ""));
      });
      this.threadsEl.appendChild(div);
    });
  }

  _threadTitle(conv) {
    const msgs = Array.isArray(conv?.messages) ? conv.messages : [];
    const firstUser = msgs.find((m) => String(m?.role || "").toLowerCase() === "user" && String(m?.content || "").trim());
    const txt = String(firstUser?.content || "").trim().replace(/\s+/g, " ");
    return txt.length > 50 ? txt.slice(0, 50) + "…" : txt;
  }

  async switchConversation(conversationId) {
    const id = String(conversationId || "").trim();
    if (!id) return;
    const db = await this.ensureDb();
    const conv = await txGet(db, STORE_CONVERSATIONS, id);
    if (conv) {
      this.conversation = conv;
      localStorage.setItem(activeConversationStorageKey(this.ctx.bookUuid, this.ctx.provider), id);
      this.renderAll();
      await this.renderThreads();
      return;
    }
    // fallback to disk
    try {
      const resp = await fetch(`/api/ai/conversations/${encodeURIComponent(this.ctx.bookUuid)}/${encodeURIComponent(id)}`);
      const data = await resp.json().catch(() => ({}));
      if (resp.ok && data?.conversation_id) {
        const loaded = {
          id: String(data.conversation_id),
          book_uuid: this.ctx.bookUuid,
          provider: this.ctx.provider,
          created_at: String(data.created_at || nowIso()),
          last_updated: String(data.last_updated || nowIso()),
          model: String(data.model || ""),
          messages: Array.isArray(data.messages)
            ? data.messages.map((m) => ({
                id: String(m.id || crypto.randomUUID()),
                conversation_id: String(data.conversation_id),
                role: m.role,
                content: m.content,
                timestamp: m.timestamp,
                metadata: m.metadata || {},
              }))
            : [],
        };
        this.conversation = loaded;
        await txPut(db, STORE_CONVERSATIONS, loaded);
        localStorage.setItem(activeConversationStorageKey(this.ctx.bookUuid, this.ctx.provider), id);
        this.renderAll();
        await this.renderThreads();
      }
    } catch {
      // ignore
    }
  }

  async newChat() {
    if (this.isBusy) return;
    const db = await this.ensureDb();
    this.conversation = {
      id: crypto.randomUUID(),
      book_uuid: this.ctx.bookUuid,
      provider: this.ctx.provider,
      model: this.currentModel || "",
      created_at: nowIso(),
      last_updated: nowIso(),
      messages: [],
    };
    await txPut(db, STORE_CONVERSATIONS, this.conversation);
    localStorage.setItem(activeConversationStorageKey(this.ctx.bookUuid, this.ctx.provider), String(this.conversation.id || ""));
    this.renderAll();
    await this.renderThreads();
    this.scheduleDiskSync();
  }

  renderAll() {
    if (!this.messagesEl) return;
    this.msgElById.clear();
    this.messagesEl.innerHTML = "";
    const msgs = (this.conversation?.messages || []).slice();
    msgs.forEach((m) => this.appendMessageToDOM(m));
    this.scrollToBottom();
  }

  scrollToBottom() {
    if (!this.messagesEl) return;
    this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
  }

  appendMessageToDOM(msg) {
    if (!this.messagesEl) return null;
    const div = document.createElement("div");
    div.className = `ai-msg ${msg.role}`;
    div.innerText = msg.content || "";

    if (msg.role === "assistant" && msg.metadata?.retrieval_sources?.length) {
      const cites = document.createElement("div");
      cites.className = "ai-citations";
      const items = msg.metadata.retrieval_sources
        .slice(0, 5)
        .map((s) => {
          const order = Number(s.chapter_order ?? s.chapter_id ?? 0);
          const title = String(s.chapter_title || "");
          const label = `第${order + 1}章 ${title}`.trim();
          return `<a href="/read/${encodeURIComponent(this.ctx.bookId)}/${order}">${escapeHtml(label)}</a>`;
        })
        .join("<br/>");
      cites.innerHTML = `<div style="font-weight:600; margin-bottom:4px;">引用</div>${items}`;
      div.appendChild(cites);
    }

    this.messagesEl.appendChild(div);
    if (msg?.id) this.msgElById.set(msg.id, div);
    return div;
  }

  async persistConversation() {
    if (!this.conversation) return;
    const db = await this.ensureDb();
    this.conversation.last_updated = nowIso();
    await txPut(db, STORE_CONVERSATIONS, this.conversation);
    this.scheduleDiskSync();
    await this.renderThreads();
  }

  scheduleDiskSync() {
    if (!this.conversation) return;
    if (this.diskSyncTimer) clearTimeout(this.diskSyncTimer);
    this.diskSyncTimer = setTimeout(() => this.syncConversationToDisk(), 600);
  }

  async syncConversationToDisk() {
    if (!this.conversation) return;
    const conv = this.conversation;
    const body = {
      provider: this.ctx.provider,
      model: this.currentModel || conv.model || "",
      created_at: conv.created_at || "",
      last_updated: conv.last_updated || "",
      messages: Array.isArray(conv.messages) ? conv.messages : [],
    };
    try {
      await fetch(`/api/ai/conversations/${encodeURIComponent(this.ctx.bookUuid)}/${encodeURIComponent(conv.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch {
      // ignore
    }
  }

  addMessage(role, content, metadata) {
    if (!this.conversation) return null;
    const msg = {
      id: crypto.randomUUID(),
      conversation_id: this.conversation.id,
      role,
      content: content || "",
      timestamp: nowIso(),
      metadata: metadata || {},
    };
    this.conversation.messages = [...(this.conversation.messages || []), msg];
    const el = this.appendMessageToDOM(msg);
    this.scrollToBottom();
    return { msg, el };
  }

  async clearConversation() {
    if (!confirm("Clear this conversation?")) return;
    if (!this.conversation?.id) return;
    this.conversation.messages = [];
    await this.persistConversation();
    this.renderAll();
  }

  async exportConversation() {
    if (this.isBusy) return;
    if (!this.conversation?.id) {
      alert("No active conversation to export. Start a new chat first.");
      return;
    }
    const fmt = String(this.exportFmtEl?.value || "md").trim().toLowerCase();
    const cid = String(this.conversation.id || "");
    const url = `/api/ai/conversations/${encodeURIComponent(this.ctx.bookUuid)}/${encodeURIComponent(cid)}/export?format=${encodeURIComponent(fmt)}`;

    try {
      if (this.exportBtn) this.exportBtn.disabled = true;
      const resp = await fetch(url);
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data?.detail || `${resp.status} ${resp.statusText}`);
      }

      let text = "";
      let mime = "text/plain";
      let ext = "txt";
      if (fmt === "json") {
        const data = await resp.json();
        text = JSON.stringify(data, null, 2);
        mime = "application/json";
        ext = "json";
      } else if (fmt === "md" || fmt === "markdown") {
        text = await resp.text();
        mime = "text/markdown";
        ext = "md";
      } else {
        text = await resp.text();
        mime = "text/plain";
        ext = "txt";
      }

      const fname = `${String(this.ctx.bookId || "book")}_${cid}.${ext}`;
      downloadText(fname, text, mime);
    } catch (err) {
      alert(`Export failed: ${err?.message || String(err)}`);
    } finally {
      if (this.exportBtn) this.exportBtn.disabled = false;
    }
  }

  async sendQuestion() {
    if (this.isBusy) return;
    const text = (this.inputEl?.value || "").trim();
    if (!text) return;
    if (!this.conversation) await this.restoreConversation();

    this.inputEl.value = "";
    this.addMessage("user", text, {});
    const placeholderWrap = this.addMessage("assistant", "…", {});
    const placeholder = placeholderWrap?.msg || null;
    const placeholderEl = placeholderWrap?.el || null;
    await this.persistConversation();

    try {
      if (this.streamingEnabled) this.abortController = new AbortController();
      this.setBusy(true);

      const history = (this.conversation.messages || []).slice(-50).map((m) => ({
        id: m.id,
        conversation_id: m.conversation_id,
        role: m.role,
        content: m.content,
        timestamp: m.timestamp,
        metadata: m.metadata || {},
      })).filter((m) => m.id !== String(placeholder?.id || ""));

      const payload = {
        question: text,
        provider: this.ctx.provider,
        model: this.currentModel || undefined,
        conversation_history: history,
        rag_k: 5,
        max_tokens: 1000,
      };

      let answer = "";
      let sources = [];
      let model = "";

      if (this.streamingEnabled) {
        const resp = await fetch(`/api/ai/question/${encodeURIComponent(this.ctx.bookUuid)}?stream=true`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          signal: this.abortController?.signal,
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          throw new Error(data?.detail || "AI request failed");
        }

        for await (const evt of streamSseResponse(resp)) {
          if (!evt) continue;
          if (evt.event === "meta") {
            sources = Array.isArray(evt.data?.retrieval_sources) ? evt.data.retrieval_sources : [];
          } else if (evt.event === "chunk") {
            const delta = String(evt.data?.delta || "");
            answer += delta;
            if (placeholder) placeholder.content = answer || "";
            if (placeholderEl) placeholderEl.innerText = answer || "";
          } else if (evt.event === "done") {
            model = String(evt.data?.model || "");
            break;
          } else if (evt.event === "error") {
            throw new Error(String(evt.data?.message || "AI request failed"));
          }
        }
      } else {
        const resp = await fetch(`/api/ai/question/${encodeURIComponent(this.ctx.bookUuid)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(data?.detail || "AI request failed");
        model = data?.metadata?.model || "";
        answer = String(data?.answer || "");
        sources = Array.isArray(data?.retrieval_sources) ? data.retrieval_sources : [];
      }

      if (model) {
        this.currentModel = model;
        localStorage.setItem(modelStorageKey(this.ctx.bookUuid, this.ctx.provider), model);
      }
      this.setProvider(this.ctx.provider, this.currentModel);

      if (placeholder) {
        placeholder.content = answer;
        placeholder.metadata = { ...(placeholder.metadata || {}), retrieval_sources: sources, model: model };
      } else {
        this.addMessage("assistant", answer, { retrieval_sources: sources, model: model });
      }
      this.renderAll();
      await this.persistConversation();
    } catch (e) {
      const msg = e?.message || String(e);
      if (placeholder) {
        placeholder.content = `Error: ${msg}`;
        if (placeholderEl) placeholderEl.innerText = placeholder.content;
      }
      else this.addMessage("assistant", `Error: ${msg}`, {});
      this.renderAll();
      await this.persistConversation();
    } finally {
      this.abortController = null;
      this.setBusy(false);
    }
  }

  async runSummary(summaryType) {
    const st = String(summaryType || "overview");
    if (this.isBusy) return;
    if (!this.conversation) await this.restoreConversation();

    this.setBusy(true);
    const placeholderWrap = this.addMessage("assistant", "生成中…", { summary_type: st });
    const placeholder = placeholderWrap?.msg || null;
    await this.persistConversation();

    try {
      const resp = await fetch(`/api/ai/summary/${encodeURIComponent(this.ctx.bookUuid)}?summary_type=${encodeURIComponent(st)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: this.ctx.provider,
          model: this.currentModel || undefined,
          max_tokens: 2000,
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data?.detail || "Summary failed");

      const model = String(data?.model || "");
      if (model) {
        this.currentModel = model;
        localStorage.setItem(modelStorageKey(this.ctx.bookUuid, this.ctx.provider), model);
      }
      this.setProvider(this.ctx.provider, this.currentModel);

      const content = data?.content || {};
      let text = "";
      if (st === "highlights") {
        const items = Array.isArray(content.highlights) ? content.highlights : [];
        text = items.map((x, i) => `${i + 1}. ${String(x)}`).join("\n");
      } else if (st === "background") {
        text = String(content.background || "");
      } else {
        text = String(content.overview || "");
      }
      if (placeholder) {
        placeholder.content = text || "(empty)";
        placeholder.metadata = { ...(placeholder.metadata || {}), model: model, summary_type: st };
      } else {
        this.addMessage("assistant", text || "(empty)", { model: model, summary_type: st });
      }
      this.renderAll();
      await this.persistConversation();

      const cacheKey = `${this.ctx.bookUuid}:${this.ctx.provider}:${model || this.currentModel || ""}`;
      if (cacheKey.endsWith(":")) return;
      const db = await this.ensureDb();
      await txPut(db, STORE_SUMMARIES, {
        cache_key: cacheKey,
        book_uuid: this.ctx.bookUuid,
        provider: this.ctx.provider,
        model: model || this.currentModel,
        generated_at: String(data?.generated_at || nowIso()),
        content: content,
      });
    } catch (e) {
      const msg = e?.message || String(e);
      if (placeholder) placeholder.content = `Error: ${msg}`;
      else this.addMessage("assistant", `Error: ${msg}`, {});
      this.renderAll();
      await this.persistConversation();
    } finally {
      this.setBusy(false);
    }
  }

  async handleAskEvent(quote, context) {
    if (!this.panel) return;
    const wasOpen = this.panel.classList.contains("is-open");
    if (!wasOpen) {
      this.open();
      await this.loadPreferences();
      await this.restoreConversation();
    }
    if (this.inputEl) {
      const ctxBlock = context ? `\n\n上下文（节选）:\n${context}` : "";
      this.inputEl.value = `引用:\n${quote}${ctxBlock}\n\n问题: `;
      this.inputEl.focus();
    }
  }
}

(function initAI() {
  const ctx = getCtx();
  if (!ctx.bookId || !ctx.bookUuid) return;
  const ui = new ReaderAIUI(ctx);
  ui.setProvider(ctx.provider, ui.currentModel);
})();
})();

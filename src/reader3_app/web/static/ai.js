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
    this.providerEl = document.getElementById("reader-ai-provider");
    this.messagesEl = document.getElementById("reader-ai-messages");
    this.inputEl = document.getElementById("reader-ai-input");
    this.sendBtn = document.getElementById("reader-ai-send");
    this.quickBtns = Array.from(document.querySelectorAll("[data-ai-summary-type]"));

    this.db = null;
    this.conversation = null;
    this.currentModel = localStorage.getItem(modelStorageKey(ctx.bookUuid, ctx.provider)) || "";
    this.isBusy = false;

    this.toggleBtn?.addEventListener("click", () => this.toggle());
    this.closeBtn?.addEventListener("click", () => this.close());
    this.clearBtn?.addEventListener("click", () => this.clearConversation());

    this.quickBtns.forEach((btn) => {
      btn.addEventListener("click", () => this.runSummary(btn.getAttribute("data-ai-summary-type")));
    });

    this.sendBtn?.addEventListener("click", () => this.sendQuestion());
    this.inputEl?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.sendQuestion();
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this.panel?.classList.contains("is-open")) this.close();
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
    await this.restoreConversation();
  }

  async restoreConversation() {
    const db = await this.ensureDb();
    const list = await txGetAllByIndex(db, STORE_CONVERSATIONS, "book_uuid_provider", [this.ctx.bookUuid, this.ctx.provider]);
    if (list.length) {
      list.sort((a, b) => String(b.last_updated || "").localeCompare(String(a.last_updated || "")));
      this.conversation = list[0];
    } else {
      this.conversation = {
        id: crypto.randomUUID(),
        book_uuid: this.ctx.bookUuid,
        provider: this.ctx.provider,
        created_at: nowIso(),
        last_updated: nowIso(),
        messages: [],
      };
      await txPut(db, STORE_CONVERSATIONS, this.conversation);
    }

    this.renderAll();
    this.setProvider(this.ctx.provider, this.currentModel);
  }

  renderAll() {
    if (!this.messagesEl) return;
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
    if (!this.messagesEl) return;
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
  }

  async persistConversation() {
    if (!this.conversation) return;
    const db = await this.ensureDb();
    this.conversation.last_updated = nowIso();
    await txPut(db, STORE_CONVERSATIONS, this.conversation);
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
    this.appendMessageToDOM(msg);
    this.scrollToBottom();
    return msg;
  }

  async clearConversation() {
    if (!confirm("Clear this conversation?")) return;
    const db = await this.ensureDb();
    if (this.conversation?.id) await txDelete(db, STORE_CONVERSATIONS, this.conversation.id);
    this.conversation = {
      id: crypto.randomUUID(),
      book_uuid: this.ctx.bookUuid,
      provider: this.ctx.provider,
      created_at: nowIso(),
      last_updated: nowIso(),
      messages: [],
    };
    await txPut(db, STORE_CONVERSATIONS, this.conversation);
    this.renderAll();
  }

  async sendQuestion() {
    if (this.isBusy) return;
    const text = (this.inputEl?.value || "").trim();
    if (!text) return;
    if (!this.conversation) await this.restoreConversation();

    this.inputEl.value = "";
    this.setBusy(true);

    this.addMessage("user", text, {});
    const placeholder = this.addMessage("assistant", "…", {});
    await this.persistConversation();

    try {
      const history = (this.conversation.messages || []).slice(-50).map((m) => ({
        id: m.id,
        conversation_id: m.conversation_id,
        role: m.role,
        content: m.content,
        timestamp: m.timestamp,
        metadata: m.metadata || {},
      }));

      const resp = await fetch(`/api/ai/question/${encodeURIComponent(this.ctx.bookUuid)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: text,
          provider: this.ctx.provider,
          model: this.currentModel || undefined,
          conversation_history: history,
          rag_k: 5,
          max_tokens: 1000,
        }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data?.detail || "AI request failed");

      const model = data?.metadata?.model || "";
      if (model) {
        this.currentModel = model;
        localStorage.setItem(modelStorageKey(this.ctx.bookUuid, this.ctx.provider), model);
      }
      this.setProvider(this.ctx.provider, this.currentModel);

      const answer = String(data?.answer || "");
      const sources = Array.isArray(data?.retrieval_sources) ? data.retrieval_sources : [];

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
      if (placeholder) placeholder.content = `Error: ${msg}`;
      else this.addMessage("assistant", `Error: ${msg}`, {});
      this.renderAll();
      await this.persistConversation();
    } finally {
      this.setBusy(false);
    }
  }

  async runSummary(summaryType) {
    const st = String(summaryType || "overview");
    if (this.isBusy) return;
    if (!this.conversation) await this.restoreConversation();

    this.setBusy(true);
    const placeholder = this.addMessage("assistant", "生成中…", { summary_type: st });
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
}

(function initAI() {
  const ctx = getCtx();
  if (!ctx.bookId || !ctx.bookUuid) return;
  const ui = new ReaderAIUI(ctx);
  ui.setProvider(ctx.provider, ui.currentModel);
})();

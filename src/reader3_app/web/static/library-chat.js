(() => {
  "use strict";

  function qs(sel, root = document) {
    return root.querySelector(sel);
  }

  function qsa(sel, root = document) {
    return Array.from(root.querySelectorAll(sel));
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function uuid() {
    try {
      return crypto.randomUUID();
    } catch {
      return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    }
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

  async function jsonFetch(url, opts = {}) {
    const resp = await fetch(url, opts);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data?.detail || `${resp.status} ${resp.statusText}`);
    }
    return data;
  }

  function parseDate(ts) {
    const d = new Date(String(ts || ""));
    return Number.isFinite(d.getTime()) ? d : null;
  }

  function formatDate(ts) {
    const d = parseDate(ts);
    if (!d) return "";
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    const min = String(d.getMinutes()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd} ${hh}:${min}`;
  }

  function compareThreads(a, b) {
    const aCreated = parseDate(a?.created_at);
    const bCreated = parseDate(b?.created_at);
    if (aCreated && bCreated) return bCreated.getTime() - aCreated.getTime();
    if (aCreated) return -1;
    if (bCreated) return 1;
    const aUpdated = parseDate(a?.last_updated);
    const bUpdated = parseDate(b?.last_updated);
    if (aUpdated && bUpdated) return bUpdated.getTime() - aUpdated.getTime();
    if (aUpdated) return -1;
    if (bUpdated) return 1;
    return String(b?.conversation_id || "").localeCompare(String(a?.conversation_id || ""));
  }

  class LibraryChat {
    constructor() {
      this.bookSelect = qs("#chat-book-select");
      this.historyWrap = qs("#chat-history");
      this.historySelect = qs("#chat-history-select");
      this.threadEl = qs("#chat-thread");
      this.inputEl = qs("#chat-input");
      this.sendBtn = qs("#chat-send-btn");
      this.stopBtn = qs("#chat-stop-btn");
      this.statusEl = qs("#chat-status");

      this.provider = document.body?.dataset?.aiDefaultProvider || "anthropic";
      this.bookId = "";
      this.bookUuid = "";
      this.conversationId = "";
      this.messages = [];
      this.isBusy = false;
      this.abortController = null;
    }

    init() {
      if (!this.bookSelect || !this.historySelect || !this.threadEl || !this.inputEl || !this.sendBtn || !this.stopBtn) {
        return;
      }

      this.bookSelect.addEventListener("change", () => this.onBookChange());
      this.historySelect.addEventListener("change", () => this.onHistoryChange());

      this.inputEl.addEventListener("input", () => this.updateComposerState());
      this.inputEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          this.send().catch(() => {});
        }
      });

      this.sendBtn.addEventListener("click", () => this.send().catch(() => {}));
      this.stopBtn.addEventListener("click", () => this.stop());

      this.updateComposerState();
    }

    setStatus(text) {
      if (!this.statusEl) return;
      this.statusEl.textContent = String(text || "");
    }

    setBusy(busy) {
      this.isBusy = Boolean(busy);
      this.updateComposerState();
    }

    updateComposerState() {
      const hasBook = Boolean(this.bookUuid);
      const hasText = Boolean((this.inputEl?.value || "").trim());
      if (this.sendBtn) this.sendBtn.disabled = !hasBook || !hasText || this.isBusy;
      if (this.stopBtn) this.stopBtn.disabled = !this.isBusy;
      if (this.inputEl) this.inputEl.disabled = !hasBook || this.isBusy;
      if (this.bookSelect) this.bookSelect.disabled = this.isBusy;
      if (this.historySelect) this.historySelect.disabled = !hasBook || this.isBusy;
    }

    appendMessage(msg) {
      this.messages.push(msg);
      this.renderMessage(msg);
      this.threadEl.scrollTop = this.threadEl.scrollHeight;
    }

    renderAll() {
      this.threadEl.innerHTML = "";
      for (const msg of this.messages) this.renderMessage(msg);
      this.threadEl.scrollTop = this.threadEl.scrollHeight;
    }

    renderMessage(msg) {
      const wrap = document.createElement("div");
      wrap.className = `chat-msg ${msg.role === "user" ? "is-user" : "is-assistant"}`;
      wrap.dataset.messageId = String(msg.id || "");

      const role = document.createElement("div");
      role.className = "chat-msg-role";
      role.textContent = msg.role === "user" ? "You" : "Assistant";

      const text = document.createElement("div");
      text.className = "chat-msg-text";
      text.textContent = String(msg.content || "");

      wrap.appendChild(role);
      wrap.appendChild(text);
      this.threadEl.appendChild(wrap);
      return { wrap, text };
    }

    newChat() {
      this.conversationId = uuid();
      this.messages = [];
      this.renderAll();
      this.setStatus("");
    }

    async onBookChange() {
      const opt = this.bookSelect.selectedOptions?.[0];
      this.bookId = String(this.bookSelect.value || "");
      this.bookUuid = String(opt?.dataset?.bookUuid || "");
      if (!this.bookUuid) {
        this.setStatus("Book UUID missing; refresh the page.");
        this.updateComposerState();
        return;
      }

      if (this.historyWrap) this.historyWrap.removeAttribute("hidden");
      await this.loadHistory();
      this.newChat();
      this.updateComposerState();
    }

    async loadHistory() {
      this.setStatus("Loading history…");
      try {
        const data = await jsonFetch(`/api/ai/conversations/${encodeURIComponent(this.bookUuid)}`);
        const threads = Array.isArray(data?.conversations) ? data.conversations : [];
        threads.sort(compareThreads);
        const top5 = threads.slice(0, 5);
        this.renderHistoryOptions(top5, this.conversationId);
        this.setStatus(top5.length ? "" : "No previous conversations for this book.");
      } catch (e) {
        this.renderHistoryOptions([], this.conversationId);
        this.setStatus(String(e?.message || "Failed to load history."));
      }
    }

    renderHistoryOptions(threads, activeConversationId) {
      this.historySelect.innerHTML = "";
      const optNew = document.createElement("option");
      optNew.value = "";
      optNew.textContent = "New chat";
      this.historySelect.appendChild(optNew);

      for (const t of threads) {
        const opt = document.createElement("option");
        opt.value = String(t.conversation_id || "");
        const title = String(t.title || "").trim() || "Conversation";
        const when = formatDate(t.created_at || t.last_updated || "");
        opt.textContent = when ? `${title} · ${when}` : title;
        this.historySelect.appendChild(opt);
      }

      const active = String(activeConversationId || "");
      this.historySelect.value = active && threads.some((t) => String(t.conversation_id || "") === active) ? active : "";
    }

    async onHistoryChange() {
      const cid = String(this.historySelect.value || "");
      if (!cid) {
        this.newChat();
        return;
      }
      await this.loadConversation(cid);
    }

    async loadConversation(conversationId) {
      this.setStatus("Loading conversation…");
      try {
        const data = await jsonFetch(
          `/api/ai/conversations/${encodeURIComponent(this.bookUuid)}/${encodeURIComponent(conversationId)}`,
        );
        const messages = Array.isArray(data?.messages) ? data.messages : [];
        this.conversationId = String(data?.conversation_id || conversationId);
        this.messages = messages.map((m) => ({
          id: String(m.id || uuid()),
          role: String(m.role || "assistant"),
          content: String(m.content || ""),
          timestamp: String(m.timestamp || ""),
          conversation_id: this.conversationId,
          metadata: m.metadata || {},
        }));
        this.renderAll();
        this.setStatus("");
      } catch (e) {
        this.setStatus(String(e?.message || "Failed to load conversation."));
      }
    }

    stop() {
      if (this.abortController) {
        try {
          this.abortController.abort();
        } catch {
          // ignore
        }
      }
      this.abortController = null;
      this.setBusy(false);
      this.setStatus("Stopped.");
    }

    async send() {
      if (this.isBusy) return;
      const text = String(this.inputEl.value || "").trim();
      if (!text || !this.bookUuid) return;
      if (!this.conversationId) this.conversationId = uuid();

      this.inputEl.value = "";

      const userMsg = {
        id: uuid(),
        role: "user",
        content: text,
        timestamp: nowIso(),
        conversation_id: this.conversationId,
        metadata: {},
      };
      this.appendMessage(userMsg);

      const placeholder = {
        id: uuid(),
        role: "assistant",
        content: "…",
        timestamp: nowIso(),
        conversation_id: this.conversationId,
        metadata: {},
      };
      this.appendMessage(placeholder);

      const placeholderWrap = this.threadEl.querySelector(`[data-message-id="${CSS.escape(placeholder.id)}"]`);
      const placeholderEl = placeholderWrap?.querySelector?.(".chat-msg-text") || null;
      const history = this.messages
        .slice(-50)
        .filter((m) => String(m.id) !== String(placeholder.id))
        .map((m) => ({
          id: m.id,
          conversation_id: this.conversationId,
          role: m.role,
          content: m.content,
          timestamp: m.timestamp,
          metadata: m.metadata || {},
        }));

      const payload = {
        question: text,
        provider: this.provider,
        conversation_history: history,
        rag_k: 5,
        max_tokens: 1000,
      };

      this.abortController = new AbortController();
      this.setBusy(true);
      this.setStatus("Thinking…");

      let serverMessageId = "";
      let answer = "";

      try {
        const resp = await fetch(`/api/ai/question/${encodeURIComponent(this.bookUuid)}?stream=true`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          signal: this.abortController.signal,
        });
        if (!resp.ok) {
          const data = await resp.json().catch(() => ({}));
          throw new Error(data?.detail || "AI request failed");
        }

        for await (const evt of streamSseResponse(resp)) {
          if (!evt) continue;
          if (evt.event === "meta") {
            serverMessageId = String(evt.data?.message_id || "");
            if (serverMessageId) {
              placeholder.id = serverMessageId;
              if (placeholderWrap) placeholderWrap.dataset.messageId = serverMessageId;
            }
          } else if (evt.event === "chunk") {
            const delta = String(evt.data?.delta || "");
            answer += delta;
            placeholder.content = answer || "";
            if (placeholderEl) placeholderEl.textContent = answer || "";
          } else if (evt.event === "done") {
            break;
          } else if (evt.event === "error") {
            throw new Error(String(evt.data?.message || "AI request failed"));
          }
        }

        // Update local state to match server message_id (so it aligns with on-disk ai_conversations).
        if (serverMessageId) {
          for (const m of this.messages) {
            if (m === placeholder) m.id = serverMessageId;
          }
        }

        this.setStatus("");
        // Refresh history so the newest conversation appears immediately.
        await this.loadHistory();
      } catch (e) {
        const msg = String(e?.message || "AI request failed");
        placeholder.content = msg;
        if (placeholderEl) placeholderEl.textContent = msg;
        this.setStatus(msg);
      } finally {
        this.abortController = null;
        this.setBusy(false);
      }
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const chat = new LibraryChat();
    chat.init();
  });
})();

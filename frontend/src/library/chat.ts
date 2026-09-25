// Library chat tab (013 WI-13; replaces static/library-chat.js). Single-book scope: pick a
// book, continue one of its five latest threads or start a new one, and stream the answer
// over SSE. The request payload and the endpoints are unchanged (the HTTP API is frozen).

// Bounded testid table (ADR-0014): literal names only.
const LIB_CHAT_MSG_TESTID = {
  user: "lib-chat-msg-user",
  assistant: "lib-chat-msg-assistant",
};

type Role = "user" | "assistant";

interface ChatMessage {
  id: string;
  role: Role;
  content: string;
  timestamp: string;
  conversation_id: string;
  metadata: Record<string, unknown>;
}

interface Thread {
  conversation_id?: string;
  title?: string;
  created_at?: string;
  last_updated?: string;
}

interface SseEvent {
  event: string;
  data: unknown;
}

function uuid(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
}

function parseSseBlock(block: string): SseEvent | null {
  let event = "message";
  let data = "";
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) event = line.slice(6).trim() || "message";
    if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  try {
    return { event, data: JSON.parse(data) as unknown };
  } catch {
    return { event, data };
  }
}

async function* streamSse(resp: Response): AsyncGenerator<SseEvent> {
  const reader = resp.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder("utf-8");
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    for (let idx = buf.indexOf("\n\n"); idx >= 0; idx = buf.indexOf("\n\n")) {
      const evt = parseSseBlock(buf.slice(0, idx));
      buf = buf.slice(idx + 2);
      if (evt) yield evt;
    }
  }
  const tail = buf.trim();
  if (tail) {
    const evt = parseSseBlock(tail);
    if (evt) yield evt;
  }
}

async function jsonFetch<T>(url: string): Promise<T> {
  const resp = await fetch(url);
  const data = (await resp.json().catch(() => ({}))) as T & { detail?: string };
  if (!resp.ok) throw new Error(data.detail || `${resp.status} ${resp.statusText}`);
  return data;
}

function parseDate(ts: unknown): Date | null {
  const d = new Date(String(ts || ""));
  return Number.isFinite(d.getTime()) ? d : null;
}

function formatDate(ts: unknown): string {
  const d = parseDate(ts);
  if (!d) return "";
  const pad = (n: number): string => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function newestFirst(a: Date | null, b: Date | null): number | null {
  if (a && b) return b.getTime() - a.getTime();
  if (a) return -1;
  if (b) return 1;
  return null;
}

function compareThreads(a: Thread, b: Thread): number {
  return (
    newestFirst(parseDate(a.created_at), parseDate(b.created_at)) ??
    newestFirst(parseDate(a.last_updated), parseDate(b.last_updated)) ??
    String(b.conversation_id || "").localeCompare(String(a.conversation_id || ""))
  );
}

function errText(e: unknown, fallback: string): string {
  return e instanceof Error && e.message ? e.message : fallback;
}

interface ChatParts {
  bookSelect: HTMLSelectElement;
  historyWrap: HTMLElement | null;
  historySelect: HTMLSelectElement;
  thread: HTMLElement;
  input: HTMLTextAreaElement;
  send: HTMLButtonElement;
  stop: HTMLButtonElement;
  status: HTMLElement | null;
}

class LibraryChat {
  private readonly provider = document.body.dataset.aiDefaultProvider || "anthropic";
  private bookUuid = "";
  private conversationId = "";
  private messages: ChatMessage[] = [];
  private busy = false;
  private abort: AbortController | null = null;

  constructor(private readonly p: ChatParts) {}

  init(): void {
    this.p.bookSelect.addEventListener("change", () => void this.onBookChange());
    this.p.historySelect.addEventListener("change", () => void this.onHistoryChange());
    this.p.input.addEventListener("input", () => this.updateComposer());
    this.p.input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        void this.sendQuestion();
      }
    });
    this.p.send.addEventListener("click", () => void this.sendQuestion());
    this.p.stop.addEventListener("click", () => this.stopStream());
    this.updateComposer();
  }

  private setStatus(text: string): void {
    if (this.p.status) this.p.status.textContent = text;
  }

  private setBusy(busy: boolean): void {
    this.busy = busy;
    this.p.send.toggleAttribute("aria-busy", busy);
    this.updateComposer();
  }

  private updateComposer(): void {
    const hasBook = Boolean(this.bookUuid);
    const hasText = Boolean(this.p.input.value.trim());
    this.p.send.disabled = !hasBook || !hasText || this.busy;
    this.p.stop.disabled = !this.busy;
    this.p.input.disabled = !hasBook || this.busy;
    this.p.bookSelect.disabled = this.busy;
    this.p.historySelect.disabled = !hasBook || this.busy;
  }

  private renderMessage(msg: ChatMessage): HTMLElement {
    const wrap = document.createElement("div");
    wrap.className = `lib-chat-msg ${msg.role === "user" ? "is-user" : "is-assistant"}`;
    wrap.dataset.testid = msg.role === "user" ? LIB_CHAT_MSG_TESTID.user : LIB_CHAT_MSG_TESTID.assistant;
    wrap.dataset.messageId = msg.id;
    const role = document.createElement("div");
    role.className = "lib-chat-role";
    role.textContent = msg.role === "user" ? "You" : "Assistant";
    const text = document.createElement("div");
    text.className = "lib-chat-text";
    text.textContent = msg.content;
    wrap.append(role, text);
    this.p.thread.append(wrap);
    return text;
  }

  private append(msg: ChatMessage): HTMLElement {
    this.messages.push(msg);
    const text = this.renderMessage(msg);
    this.p.thread.scrollTop = this.p.thread.scrollHeight;
    return text;
  }

  private renderAll(): void {
    this.p.thread.replaceChildren();
    for (const msg of this.messages) this.renderMessage(msg);
    this.p.thread.scrollTop = this.p.thread.scrollHeight;
  }

  private newChat(): void {
    this.conversationId = uuid();
    this.messages = [];
    this.renderAll();
    this.setStatus("");
  }

  private async onBookChange(): Promise<void> {
    const opt = this.p.bookSelect.selectedOptions[0];
    this.bookUuid = opt?.dataset.bookUuid || "";
    if (!this.bookUuid) {
      this.setStatus("Book UUID missing; refresh the page.");
      this.updateComposer();
      return;
    }
    if (this.p.historyWrap) this.p.historyWrap.hidden = false;
    await this.loadHistory();
    this.newChat();
    this.updateComposer();
  }

  private async loadHistory(): Promise<void> {
    this.setStatus("Loading history…");
    try {
      const data = await jsonFetch<{ conversations?: Thread[] }>(`/api/ai/conversations/${encodeURIComponent(this.bookUuid)}`);
      const threads = (Array.isArray(data.conversations) ? data.conversations : []).sort(compareThreads).slice(0, 5);
      this.renderHistory(threads);
      this.setStatus(threads.length ? "" : "No previous conversations for this book.");
    } catch (e) {
      this.renderHistory([]);
      this.setStatus(errText(e, "Failed to load history."));
    }
  }

  private renderHistory(threads: Thread[]): void {
    const fresh = document.createElement("option");
    fresh.value = "";
    fresh.textContent = "New chat";
    const options = threads.map((t) => {
      const opt = document.createElement("option");
      opt.value = String(t.conversation_id || "");
      const title = String(t.title || "").trim() || "Conversation";
      const when = formatDate(t.created_at || t.last_updated || "");
      opt.textContent = when ? `${title} · ${when}` : title;
      return opt;
    });
    this.p.historySelect.replaceChildren(fresh, ...options);
    const active = this.conversationId;
    this.p.historySelect.value = active && threads.some((t) => String(t.conversation_id || "") === active) ? active : "";
  }

  private async onHistoryChange(): Promise<void> {
    const cid = this.p.historySelect.value;
    if (!cid) {
      this.newChat();
      return;
    }
    this.setStatus("Loading conversation…");
    try {
      const data = await jsonFetch<{ conversation_id?: string; messages?: Array<Partial<ChatMessage>> }>(
        `/api/ai/conversations/${encodeURIComponent(this.bookUuid)}/${encodeURIComponent(cid)}`,
      );
      this.conversationId = String(data.conversation_id || cid);
      this.messages = (Array.isArray(data.messages) ? data.messages : []).map((m) => ({
        id: String(m.id || uuid()),
        role: m.role === "user" ? "user" : "assistant",
        content: String(m.content || ""),
        timestamp: String(m.timestamp || ""),
        conversation_id: this.conversationId,
        metadata: m.metadata || {},
      }));
      this.renderAll();
      this.setStatus("");
    } catch (e) {
      this.setStatus(errText(e, "Failed to load conversation."));
    }
  }

  private stopStream(): void {
    this.abort?.abort();
    this.abort = null;
    this.setBusy(false);
    this.setStatus("Stopped.");
  }

  private message(role: Role, content: string): ChatMessage {
    return { id: uuid(), role, content, timestamp: new Date().toISOString(), conversation_id: this.conversationId, metadata: {} };
  }

  private async sendQuestion(): Promise<void> {
    if (this.busy) return;
    const text = this.p.input.value.trim();
    if (!text || !this.bookUuid) return;
    if (!this.conversationId) this.conversationId = uuid();
    this.p.input.value = "";

    this.append(this.message("user", text));
    const placeholder = this.message("assistant", "…");
    const placeholderText = this.append(placeholder);
    const history = this.messages
      .slice(-50)
      .filter((m) => m !== placeholder)
      .map((m) => ({ ...m, conversation_id: this.conversationId }));
    const payload = { question: text, provider: this.provider, conversation_history: history, rag_k: 5, max_tokens: 1000 };

    const controller = new AbortController();
    this.abort = controller;
    this.setBusy(true);
    this.setStatus("Thinking…");
    let answer = "";
    try {
      const resp = await fetch(`/api/ai/question/${encodeURIComponent(this.bookUuid)}?stream=true`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      if (!resp.ok) {
        const data = (await resp.json().catch(() => ({}))) as { detail?: string };
        throw new Error(data.detail || "AI request failed");
      }
      for await (const evt of streamSse(resp)) {
        const data = (evt.data ?? {}) as { message_id?: string; delta?: string; message?: string };
        if (evt.event === "meta") {
          const serverId = String(data.message_id || "");
          if (serverId) {
            placeholder.id = serverId;
            if (placeholderText.parentElement) placeholderText.parentElement.dataset.messageId = serverId;
          }
        } else if (evt.event === "chunk") {
          answer += String(data.delta || "");
          placeholder.content = answer;
          placeholderText.textContent = answer;
        } else if (evt.event === "done") {
          break;
        } else if (evt.event === "error") {
          throw new Error(String(data.message || "AI request failed"));
        }
      }
      this.setStatus("");
      await this.loadHistory();
    } catch (e) {
      // Stop already said "Stopped." and left the placeholder (or the partial answer) as it
      // was; the AbortError the aborted request throws is that stop, not a failure to report.
      if (controller.signal.aborted) return;
      const msg = errText(e, "AI request failed");
      placeholder.content = msg;
      placeholderText.textContent = msg;
      this.setStatus(msg);
    } finally {
      // A stop has already released the composer; a newer question may own this.abort now.
      if (this.abort === controller) {
        this.abort = null;
        this.setBusy(false);
      }
    }
  }
}

export function initLibraryChat(): void {
  const get = <T extends HTMLElement>(id: string): T | null => document.getElementById(id) as T | null;
  const bookSelect = get<HTMLSelectElement>("chat-book-select");
  const historySelect = get<HTMLSelectElement>("chat-history-select");
  const thread = get<HTMLElement>("chat-thread");
  const input = get<HTMLTextAreaElement>("chat-input");
  const send = get<HTMLButtonElement>("chat-send-btn");
  const stop = get<HTMLButtonElement>("chat-stop-btn");
  if (!bookSelect || !historySelect || !thread || !input || !send || !stop) return;
  new LibraryChat({
    bookSelect,
    historySelect,
    thread,
    input,
    send,
    stop,
    historyWrap: get<HTMLElement>("chat-history"),
    status: get<HTMLElement>("chat-status"),
  }).init();
}

// 013 final review L1 (RV-3): the library chat's Stop.
//   After stopStream, the AbortError the aborted fetch / body read throws must not overwrite
//   the "Stopped." status, nor replace the assistant placeholder (or the partial answer it
//   already shows) with an error message.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { initLibraryChat } from "../../src/library/chat";

const CHUNK = 'event: chunk\ndata: {"delta":"Partial"}\n\n';

function mount(): void {
  document.body.innerHTML = `
    <select id="chat-book-select">
      <option value="">Pick a book</option>
      <option value="b1" data-book-uuid="u1">Book one</option>
    </select>
    <div id="chat-history" hidden><select id="chat-history-select"></select></div>
    <div id="chat-thread"></div>
    <textarea id="chat-input"></textarea>
    <button type="button" id="chat-send-btn">Send</button>
    <button type="button" id="chat-stop-btn">Stop</button>
    <div id="chat-status"></div>`;
}

const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T;
const status = (): string => $("chat-status").textContent ?? "";
const assistantText = (): string =>
  document.querySelector('[data-testid="lib-chat-msg-assistant"] .lib-chat-text')?.textContent ?? "";

/** A streaming answer that sends `chunks`, then hangs until the request is aborted. */
function streamingFetch(chunks: string[]): typeof fetch {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.startsWith("/api/ai/conversations/")) {
      return new Response(JSON.stringify({ conversations: [] }), { status: 200 });
    }
    const signal = init?.signal;
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        const enc = new TextEncoder();
        for (const c of chunks) controller.enqueue(enc.encode(c));
        signal?.addEventListener("abort", () =>
          controller.error(new DOMException("The operation was aborted.", "AbortError")),
        );
      },
    });
    return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
  }) as unknown as typeof fetch;
}

async function settle(): Promise<void> {
  for (let i = 0; i < 10; i += 1) await new Promise((r) => setTimeout(r, 0));
}

async function ask(): Promise<void> {
  const book = $<HTMLSelectElement>("chat-book-select");
  book.value = "b1";
  book.dispatchEvent(new Event("change"));
  await vi.waitFor(() => expect($<HTMLTextAreaElement>("chat-input").disabled).toBe(false));
  const input = $<HTMLTextAreaElement>("chat-input");
  input.value = "What happens?";
  input.dispatchEvent(new Event("input"));
  $<HTMLButtonElement>("chat-send-btn").click();
}

beforeEach(() => {
  mount();
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

describe("Stop during a streamed answer", () => {
  it("keeps the partial answer and the Stopped. status after the AbortError lands", async () => {
    vi.stubGlobal("fetch", streamingFetch([CHUNK]));
    initLibraryChat();
    await ask();
    await vi.waitFor(() => expect(assistantText()).toBe("Partial"));

    $<HTMLButtonElement>("chat-stop-btn").click();
    await settle();

    expect(status()).toBe("Stopped.");
    expect(assistantText()).toBe("Partial");
    expect($<HTMLButtonElement>("chat-stop-btn").disabled).toBe(true);
  });

  it("keeps the placeholder when Stop comes before the first chunk", async () => {
    vi.stubGlobal("fetch", streamingFetch([]));
    initLibraryChat();
    await ask();
    await vi.waitFor(() => expect(status()).toBe("Thinking…"));
    await settle();

    $<HTMLButtonElement>("chat-stop-btn").click();
    await settle();

    expect(status()).toBe("Stopped.");
    expect(assistantText()).toBe("…");
  });
});

// 013 final review RV-12: a non-abort failure must be reported, not swallowed like a Stop.
//   Both the HTTP-error path and the SSE `event: error` path end in the catch at chat.ts's
//   sendQuestion; a catch that just returns would leave the status on "Thinking…" and the
//   placeholder on "…".
function answerFetch(answer: () => Response): typeof fetch {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith("/api/ai/conversations/")) {
      return new Response(JSON.stringify({ conversations: [] }), { status: 200 });
    }
    return answer();
  }) as unknown as typeof fetch;
}

describe("A failed answer that was not stopped", () => {
  it("shows the server's detail when the request returns a 500", async () => {
    vi.stubGlobal(
      "fetch",
      answerFetch(
        () =>
          new Response(JSON.stringify({ detail: "x" }), {
            status: 500,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );
    initLibraryChat();
    await ask();
    await vi.waitFor(() => expect(status()).toBe("x"));

    expect(assistantText()).toBe("x");
    expect(assistantText()).not.toBe("…");
    expect($<HTMLButtonElement>("chat-stop-btn").disabled).toBe(true);
  });

  it("shows the stream's error message when the SSE stream sends event: error", async () => {
    vi.stubGlobal(
      "fetch",
      answerFetch(
        () =>
          new Response('event: error\ndata: {"message":"provider exploded"}\n\n', {
            status: 200,
            headers: { "Content-Type": "text/event-stream" },
          }),
      ),
    );
    initLibraryChat();
    await ask();
    await vi.waitFor(() => expect(status()).toBe("provider exploded"));

    expect(assistantText()).toBe("provider exploded");
    expect(assistantText()).not.toBe("…");
    expect($<HTMLButtonElement>("chat-stop-btn").disabled).toBe(true);
  });
});

// 013 WI-12 (fe-unit half of C12.01 / C12.02): the shared confirm dialog over <dialog>.
//   * open: the dialog is modal-open and focus is inside it (on cancel: the safe default)
//   * cancel / close button / a native close (Esc) / a backdrop click close it, never run
//     the primary action, and return focus to the trigger
//   * primary is single-flight: any burst of clicks while the action is pending runs it once;
//     the control is disabled + aria-busy while pending, and usable again on the next open
//   * Tab and Shift+Tab wrap inside the dialog
// jsdom has no HTMLDialogElement.showModal / close; the polyfill below gives them the two
// observable effects the module relies on (the `open` attribute and the `close` event).
import fc from "fast-check";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { bindModal, type ModalParts } from "../../src/components/modal";

beforeAll(() => {
  const proto = HTMLDialogElement.prototype as HTMLDialogElement & {
    showModal: () => void;
    close: (value?: string) => void;
  };
  proto.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  proto.close = function close(this: HTMLDialogElement) {
    if (!this.hasAttribute("open")) return;
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
});

interface Fixture {
  trigger: HTMLButtonElement;
  parts: ModalParts;
  body: HTMLParagraphElement;
}

function mount(): Fixture {
  document.body.innerHTML = `
    <button type="button" id="trigger">Delete all</button>
    <button type="button" id="elsewhere">Elsewhere</button>
    <dialog id="dlg">
      <header><h2>Title</h2><button type="button" id="close">×</button></header>
      <p id="body">Body text</p>
      <footer>
        <button type="button" id="cancel">Cancel</button>
        <button type="button" id="primary">Delete</button>
      </footer>
    </dialog>`;
  const q = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
  return {
    trigger: q<HTMLButtonElement>("trigger"),
    body: q<HTMLParagraphElement>("body"),
    parts: {
      dialog: q<HTMLDialogElement>("dlg"),
      close: q<HTMLButtonElement>("close"),
      cancel: q<HTMLButtonElement>("cancel"),
      primary: q<HTMLButtonElement>("primary"),
    },
  };
}

function deferred(): { promise: Promise<void>; resolve: () => void } {
  let resolve!: () => void;
  const promise = new Promise<void>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

function openFrom(f: Fixture, ctrl: ReturnType<typeof bindModal>): void {
  f.trigger.focus();
  ctrl.open(f.trigger);
}

function press(key: string, shiftKey = false): KeyboardEvent {
  const ev = new KeyboardEvent("keydown", { key, shiftKey, bubbles: true, cancelable: true });
  (document.activeElement ?? document.body).dispatchEvent(ev);
  return ev;
}

let f: Fixture;

beforeEach(() => {
  f = mount();
});

afterEach(() => {
  document.body.replaceChildren();
});

describe("open", () => {
  it("opens the dialog and moves focus inside, onto cancel", () => {
    const ctrl = bindModal(f.parts, vi.fn());
    openFrom(f, ctrl);
    expect(f.parts.dialog.hasAttribute("open")).toBe(true);
    expect(ctrl.isOpen).toBe(true);
    expect(document.activeElement).toBe(f.parts.cancel);
  });
});

describe("dismiss paths never run the action and return focus", () => {
  const paths: Array<[string, (fx: Fixture) => void]> = [
    ["cancel", (fx) => fx.parts.cancel.click()],
    ["close button", (fx) => fx.parts.close.click()],
    ["native close (Esc)", (fx) => fx.parts.dialog.close()],
    [
      "backdrop click",
      (fx) =>
        fx.parts.dialog.dispatchEvent(new MouseEvent("click", { bubbles: true, clientX: 2, clientY: 2 })),
    ],
  ];

  it.each(paths)("%s", (_name, dismiss) => {
    const action = vi.fn();
    const ctrl = bindModal(f.parts, action);
    openFrom(f, ctrl);
    f.parts.cancel.focus();
    dismiss(f);
    expect(f.parts.dialog.hasAttribute("open")).toBe(false);
    expect(ctrl.isOpen).toBe(false);
    expect(action).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(f.trigger);
  });

  it("a click on the dialog's own content is not a backdrop click", () => {
    const ctrl = bindModal(f.parts, vi.fn());
    openFrom(f, ctrl);
    f.body.click();
    expect(f.parts.dialog.hasAttribute("open")).toBe(true);
  });
});

describe("primary is single-flight", () => {
  it("three clicks while pending run the action once, then the dialog closes", async () => {
    const d = deferred();
    const action = vi.fn(() => d.promise);
    const ctrl = bindModal(f.parts, action);
    openFrom(f, ctrl);
    f.parts.primary.click();
    f.parts.primary.click();
    f.parts.primary.click();
    expect(action).toHaveBeenCalledTimes(1);
    expect(f.parts.primary.disabled).toBe(true);
    expect(f.parts.primary.getAttribute("aria-busy")).toBe("true");
    d.resolve();
    await vi.waitFor(() => expect(f.parts.dialog.hasAttribute("open")).toBe(false));
    expect(f.parts.primary.disabled).toBe(false);
    expect(f.parts.primary.getAttribute("aria-busy")).not.toBe("true");
    expect(document.activeElement).toBe(f.trigger);
  });

  it("a rejected action still closes and releases the control", async () => {
    const action = vi.fn(() => Promise.reject(new Error("boom")));
    const ctrl = bindModal(f.parts, action);
    openFrom(f, ctrl);
    f.parts.primary.click();
    await vi.waitFor(() => expect(f.parts.dialog.hasAttribute("open")).toBe(false));
    expect(f.parts.primary.disabled).toBe(false);
    expect(action).toHaveBeenCalledTimes(1);
  });

  it("for any burst size on any number of opens, each open runs the action exactly once", async () => {
    await fc.assert(
      fc.asyncProperty(fc.array(fc.integer({ min: 1, max: 8 }), { minLength: 1, maxLength: 4 }), async (bursts) => {
        f = mount();
        const action = vi.fn(async () => {});
        const ctrl = bindModal(f.parts, action);
        for (const n of bursts) {
          openFrom(f, ctrl);
          for (let i = 0; i < n; i += 1) f.parts.primary.click();
          await vi.waitFor(() => expect(f.parts.dialog.hasAttribute("open")).toBe(false));
        }
        expect(action).toHaveBeenCalledTimes(bursts.length);
      }),
      { numRuns: 25 },
    );
  });
});

describe("Esc while the action is pending (013 final review, RV-8)", () => {
  // A real `cancel` event, as the browser fires it for Esc, followed by what the browser does
  // next: close the dialog unless the event was cancelled.
  function pressEsc(dialog: HTMLDialogElement): Event {
    const ev = new Event("cancel", { cancelable: true });
    dialog.dispatchEvent(ev);
    if (!ev.defaultPrevented) dialog.close();
    return ev;
  }

  it("a cancel event while busy is refused and the dialog stays open", async () => {
    const d = deferred();
    const action = vi.fn(() => d.promise);
    const ctrl = bindModal(f.parts, action);
    openFrom(f, ctrl);
    f.parts.primary.click();
    expect(f.parts.primary.getAttribute("aria-busy")).toBe("true");

    const ev = pressEsc(f.parts.dialog);
    expect(ev.defaultPrevented).toBe(true);
    expect(f.parts.dialog.hasAttribute("open")).toBe(true);
    expect(ctrl.isOpen).toBe(true);

    d.resolve();
    await vi.waitFor(() => expect(f.parts.dialog.hasAttribute("open")).toBe(false));
    expect(action).toHaveBeenCalledTimes(1);
    expect(document.activeElement).toBe(f.trigger);
  });

  it("a cancel event when idle is let through and closes the dialog", () => {
    const action = vi.fn();
    const ctrl = bindModal(f.parts, action);
    openFrom(f, ctrl);
    const ev = pressEsc(f.parts.dialog);
    expect(ev.defaultPrevented).toBe(false);
    expect(f.parts.dialog.hasAttribute("open")).toBe(false);
    expect(action).not.toHaveBeenCalled();
  });
});

describe("focus trap", () => {
  it("Tab from the last control wraps to the first; Shift+Tab from the first wraps to the last", () => {
    const ctrl = bindModal(f.parts, vi.fn());
    openFrom(f, ctrl);
    f.parts.primary.focus();
    const tab = press("Tab");
    expect(tab.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(f.parts.close);
    const back = press("Tab", true);
    expect(back.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(f.parts.primary);
  });

  it("Tab in the middle is left to the browser", () => {
    const ctrl = bindModal(f.parts, vi.fn());
    openFrom(f, ctrl);
    f.parts.cancel.focus();
    expect(press("Tab").defaultPrevented).toBe(false);
  });
});

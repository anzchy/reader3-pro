// Shared confirm dialog over a native <dialog> (013 WI-12; A12.2, FP-15).
//
// The markup (title, body, close / cancel / primary buttons, testids) lives in the template;
// this module only binds behaviour to it:
//
// * open(trigger): showModal(), focus moves inside onto cancel (the safe default)
// * cancel, the close button, Esc (the native `cancel` -> `close`) and a click on the backdrop
//   close the dialog without running the action; focus returns to the trigger
// * primary is single-flight: while the action is pending the button is disabled and
//   aria-busy, further clicks are ignored, and the dismiss paths are held off so the action
//   finishes before focus moves back. Settled (resolved or rejected), the control is released
//   and the dialog closes. The action reports its own outcome; a rejection is swallowed here.
// * Tab / Shift+Tab wrap between the first and last enabled controls of the dialog.

export interface ModalParts {
  dialog: HTMLDialogElement;
  close: HTMLElement;
  cancel: HTMLElement;
  primary: HTMLButtonElement;
}

export interface ModalController {
  open(trigger?: HTMLElement | null): void;
  close(): void;
  readonly isOpen: boolean;
}

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusables(dialog: HTMLDialogElement): HTMLElement[] {
  return Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE));
}

function outside(rect: DOMRect, x: number, y: number): boolean {
  return x < rect.left || x > rect.right || y < rect.top || y > rect.bottom;
}

export function bindModal(parts: ModalParts, onPrimary: () => void | Promise<void>): ModalController {
  const { dialog, close, cancel, primary } = parts;
  let trigger: HTMLElement | null = null;
  let busy = false;

  const isOpen = (): boolean => dialog.hasAttribute("open");

  const dismiss = (): void => {
    if (busy || !isOpen()) return;
    dialog.close();
  };

  const setBusy = (value: boolean): void => {
    busy = value;
    primary.disabled = value;
    if (value) primary.setAttribute("aria-busy", "true");
    else primary.removeAttribute("aria-busy");
  };

  dialog.addEventListener("close", () => {
    const back = trigger;
    trigger = null;
    if (back && back.isConnected) back.focus();
  });

  // Esc: the browser fires `cancel`, then closes. Held off while the action runs.
  dialog.addEventListener("cancel", (event) => {
    if (busy) event.preventDefault();
  });

  close.addEventListener("click", dismiss);
  cancel.addEventListener("click", dismiss);

  // A modal dialog's backdrop hit-tests as the dialog itself: a click whose target is the
  // dialog and whose point lies outside its box is a backdrop click.
  dialog.addEventListener("click", (event) => {
    if (event.target !== dialog) return;
    if (outside(dialog.getBoundingClientRect(), event.clientX, event.clientY)) dismiss();
  });

  dialog.addEventListener("keydown", (event) => {
    if (event.key !== "Tab") return;
    const items = focusables(dialog);
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    const inside = active instanceof HTMLElement && dialog.contains(active) && active !== dialog;
    if (event.shiftKey && (!inside || active === first)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (!inside || active === last)) {
      event.preventDefault();
      first.focus();
    }
  });

  primary.addEventListener("click", () => {
    if (busy || !isOpen()) return;
    setBusy(true);
    void (async () => {
      try {
        await onPrimary();
      } catch {
        // the action reports its own failure (a result line on the page)
      } finally {
        setBusy(false);
        if (isOpen()) dialog.close();
      }
    })();
  });

  return {
    open(from?: HTMLElement | null): void {
      if (isOpen()) return;
      trigger = from ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
      dialog.showModal();
      cancel.focus();
    },
    close: dismiss,
    get isOpen() {
      return isOpen();
    },
  };
}

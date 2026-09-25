// The Toast (013 WI-11; design spec §5.3). Replaces showToast from static/js/annotations.js.
//
// Rules this file carries, each from spec §5.3:
//   * At most one toast; a new one replaces the old and restarts the dwell. "At most one toast"
//     and "at most one container element" are therefore the same query (WI-11 acceptance 4).
//   * The dwell is `--r3-dwell-toast`, read through getComputedStyle at show time. It is reading
//     time, not animation time: it must never derive from the transition-duration token family,
//     which drops to 0ms under prefers-reduced-motion and would make the toast vanish on mount
//     (acceptance 4a; spec §3.5.3 exception 3).
//   * aria-live="polite" + aria-atomic="true" sit on a persistent region, not on the toast; no
//     role at all (never role="alert", which is assertive).
//   * No inline styles: layout, stacking (the toast layer token) and tone colours live in CSS.
//   * The testid is supplied by the page (lib-toast / rd-toast; ADR-0013 prefixes), never
//     hardcoded here.
import "../components/toast.css";
export type ToastTestId = "lib-toast" | "rd-toast";
export type ToastTone = "success" | "error" | "info";

export interface ToastOptions {
  testId: ToastTestId;
  tone?: ToastTone;
}

const DWELL_TOKEN = "--r3-dwell-toast";
const TIME_RE = /^(\d+(?:\.\d+)?)(ms|s)$/;

let region: HTMLElement | null = null;
let timer: ReturnType<typeof setTimeout> | null = null;

/**
 * The toast dwell in milliseconds, from the resolved `--r3-dwell-toast` on `root`.
 * Throws when the token is missing, unparseable or not positive: guessing a constant here
 * would silently detach the dwell from its single definition in the token layer.
 */
export function readToastDwellMs(root: Element = document.documentElement): number {
  const raw = getComputedStyle(root).getPropertyValue(DWELL_TOKEN).trim();
  const m = TIME_RE.exec(raw);
  const ms = m ? Number(m[1]) * (m[2] === "s" ? 1000 : 1) : Number.NaN;
  if (!(ms > 0)) {
    throw new Error(`${DWELL_TOKEN} did not resolve to a positive CSS time (got ${JSON.stringify(raw)})`);
  }
  return ms;
}

function ensureRegion(): HTMLElement {
  if (region?.isConnected) return region;
  const el = document.createElement("div");
  el.className = "r3-toast-region";
  el.setAttribute("aria-live", "polite");
  el.setAttribute("aria-atomic", "true");
  document.body.append(el);
  region = el;
  return el;
}

/** Show `message` as the one toast on the page, replacing any current toast. */
export function showToast(message: string, options: ToastOptions): HTMLElement {
  const dwell = readToastDwellMs();
  if (timer !== null) {
    clearTimeout(timer);
    timer = null;
  }
  const el = document.createElement("div");
  el.className = `r3-toast r3-toast--${options.tone ?? "info"}`;
  el.dataset.testid = options.testId;
  el.textContent = message;
  ensureRegion().replaceChildren(el);
  timer = setTimeout(() => {
    el.remove();
    timer = null;
  }, dwell);
  return el;
}

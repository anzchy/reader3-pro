// Gated diagnostic output (013 WI-11, ET-10). Replaces ad-hoc console.log calls: off unless
// localStorage["reader3.debug"] === "1", read on every call so it can be toggled in a live tab.
//
// This file is the only place in frontend/src allowed to write console.info / console.debug
// (eslint.config.js grants it by file); console.log is allowed nowhere. warn / error are not
// debug output and are used directly where needed.
export const DEBUG_STORAGE_KEY = "reader3.debug";

function enabled(): boolean {
  try {
    return globalThis.localStorage?.getItem(DEBUG_STORAGE_KEY) === "1";
  } catch {
    // Storage can throw (sandboxed iframes, disabled storage). Diagnostics are never worth
    // breaking the caller for, so treat it as off.
    return false;
  }
}

export const debug = {
  /** Routine diagnostics: the replacement for the legacy console.log calls. */
  log(...args: unknown[]): void {
    if (enabled()) console.info(...args);
  },
  /** High-volume tracing (per-event, per-frame); lands in the browser's "Verbose" level. */
  verbose(...args: unknown[]): void {
    if (enabled()) console.debug(...args);
  },
};

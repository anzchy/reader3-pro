// The chrome colour scheme, shared by the settings page and the library header toggle
// (013 WI-12 moved here in WI-13 so both surfaces hold one state; C13.33).
//
// The key is the one the FOUC script in every template reads, so a choice made anywhere
// applies on the next page load before first paint. Only `data-theme` is written;
// `data-reading-theme` (the reader's paper axis) belongs to the reader and is never touched.

/** The chrome-scheme storage key, shared with the templates' FOUC script. */
export const SCHEME_KEY = "reader3.ui.colorScheme";

export type Scheme = "system" | "light" | "dark";

export const SCHEMES: readonly Scheme[] = ["system", "light", "dark"];

function isScheme(value: unknown): value is Scheme {
  return typeof value === "string" && (SCHEMES as readonly string[]).includes(value);
}

/** The stored scheme; anything absent, unknown or unreadable is "system". Never writes. */
export function readScheme(storage: Storage | null): Scheme {
  if (!storage) return "system";
  try {
    const value = storage.getItem(SCHEME_KEY);
    return isScheme(value) ? value : "system";
  } catch {
    return "system";
  }
}

/**
 * Put `scheme` on the root (system removes `data-theme`) and remember it, "system" included.
 * A storage that throws (private mode, blocked cookies) still gets the attribute applied.
 */
export function applyScheme(scheme: Scheme, root: HTMLElement, storage: Storage | null): void {
  if (scheme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", scheme);
  if (!storage) return;
  try {
    storage.setItem(SCHEME_KEY, scheme);
  } catch {
    // the attribute is applied; the choice just does not survive a reload
  }
}

/** The next scheme in the header toggle's cycle: system -> light -> dark -> system. */
export function nextScheme(scheme: Scheme): Scheme {
  return SCHEMES[(SCHEMES.indexOf(scheme) + 1) % SCHEMES.length];
}

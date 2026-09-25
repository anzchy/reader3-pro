// Pure helpers of the settings page (013 WI-12).
//
// * clampInt: the RAG number inputs (FB-S07). Always an integer in [min, max]; empty or
//   non-numeric input gives the fallback.
// * readScheme / applyScheme: the chrome colour scheme (A12.6-A12.8). Since 013 WI-13 they live
//   in @shared/scheme (the library header toggle shares the state) and are re-exported here, the
//   same function objects, so existing imports keep working.

export { SCHEME_KEY, SCHEMES, applyScheme, readScheme, type Scheme } from "@shared/scheme";

/** `raw` rounded to an integer and clamped to [min, max]; `fallback` when it is not a number. */
export function clampInt(raw: string | number, min: number, max: number, fallback: number): number {
  const text = typeof raw === "number" ? String(raw) : raw.trim();
  if (text === "") return fallback;
  const value = Number(text);
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, Math.round(value))) + 0; // + 0 folds -0 into 0
}

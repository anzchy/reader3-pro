// The single index-status table (013 WI-13; Track-D WI-3 #1/#5). Every page that shows a
// book's index status reads its label and allowed actions from here; nothing else defines one.
//
// normalizeIndexStatus is total. `GET /api/index/{id}/status` answers a status among the four
// real ones plus a `stale` flag; `stale: true` wins, and anything outside the enum (a missing
// field, a non-string, a future status, a bare "stale" string) is "unknown". The legacy
// `|| "not_indexed"` fallback made an unreadable status look like a book that had never been
// indexed and offered to index it again; "unknown" offers nothing.
export type IndexState = "not_indexed" | "indexing" | "indexed" | "error" | "stale" | "unknown";

export interface StatusMetaEntry {
  /** What the pill reads. */
  label: string;
  /** Whether the UI may offer 「开始索引」 for a book in this state. */
  canStartIndex: boolean;
}

export const INDEX_STATES: readonly IndexState[] = ["not_indexed", "indexing", "indexed", "error", "stale", "unknown"];

const REAL_STATES: readonly string[] = ["not_indexed", "indexing", "indexed", "error"];

export const statusMeta: Readonly<Record<IndexState, StatusMetaEntry>> = Object.freeze({
  not_indexed: { label: "未索引", canStartIndex: true },
  indexing: { label: "索引中…", canStartIndex: false },
  indexed: { label: "已索引", canStartIndex: false },
  error: { label: "索引失败", canStartIndex: false },
  stale: { label: "索引已过期", canStartIndex: false },
  unknown: { label: "状态未知", canStartIndex: false },
});

export function normalizeIndexStatus(payload: unknown): IndexState {
  if (typeof payload !== "object" || payload === null) return "unknown";
  const record = payload as { status?: unknown; stale?: unknown };
  if (record.stale === true) return "stale";
  const status = record.status;
  return typeof status === "string" && REAL_STATES.includes(status) ? (status as IndexState) : "unknown";
}

// The single definition of HTML escaping (013 WI-11, ET-9; plan §WI-11 ruling). The four legacy
// copies in static/*.js split into two groups with the same five characters and no security
// difference; this takes group B's nullish semantics (null / undefined render as "", not
// "null") and group A's replaceAll style. Any change to the semantics happens here, nowhere else.
//
// `&` is replaced first so that the entities produced by the later replacements are not
// escaped a second time. `&#39;` and `&#039;` are equivalent; `&#39;` is the chosen spelling.
export function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

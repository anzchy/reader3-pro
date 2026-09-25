// Skeleton placeholder (Track-D WI-8, hosted in 013 WI-13). A presentational block that holds
// the place of content still loading. It is hidden from assistive technology (the loading
// state is announced by the owner, not by each block) and carries no test hook of its own:
// a test finds the owner, not the placeholder (Track-D WI-8 #1).
import "./skeleton.css";

export function createSkeleton(label?: string): HTMLSpanElement {
  const el = document.createElement("span");
  el.className = "r3-skeleton";
  el.setAttribute("aria-hidden", "true");
  if (label) el.title = label;
  return el;
}

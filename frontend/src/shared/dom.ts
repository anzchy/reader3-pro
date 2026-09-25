// Small DOM helpers shared by the pages (013 WI-11). getEventTargetElement and
// elementDebugInfo moved here from static/js/annotations.js.
export interface ElementDebugInfo {
  tag: string;
  id: string;
  className: string;
  pointerEvents: string;
  position: string;
  zIndex: string;
}

/** The element an event target stands for: a text node maps to its parent element. */
export function getEventTargetElement(target: EventTarget | Node | null | undefined): Element | null {
  // Window and other non-node targets have no numeric nodeType.
  const node = target as Node | null | undefined;
  if (!node || typeof node.nodeType !== "number") return null;
  if (node.nodeType === Node.TEXT_NODE) return node.parentElement;
  if (node.nodeType === Node.ELEMENT_NODE) return node as Element;
  return null;
}

/** A plain snapshot of the properties that decide whether an element intercepts pointers. */
export function elementDebugInfo(el: Element | null | undefined): ElementDebugInfo | null {
  if (!el) return null;
  let style: CSSStyleDeclaration | null = null;
  try {
    const view = el.ownerDocument?.defaultView ?? window;
    style = view.getComputedStyle(el);
  } catch {
    style = null;
  }
  return {
    tag: el.tagName,
    id: el.id || "",
    className: typeof el.className === "string" ? el.className : "",
    pointerEvents: style ? style.pointerEvents : "",
    position: style ? style.position : "",
    zIndex: style ? style.zIndex : "",
  };
}

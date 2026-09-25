// Page boot marker shared by the three entries (013 WI-9). Stamps which TS entry
// booted on the root element; nothing else. Pages grow real boot logic in WI-12/13/16.
export const PAGE_NAMES = ["library", "reader", "settings"] as const;

export type PageName = (typeof PAGE_NAMES)[number];

export function markBooted(page: PageName, root: HTMLElement = document.documentElement): void {
  root.dataset.r3Page = page;
}

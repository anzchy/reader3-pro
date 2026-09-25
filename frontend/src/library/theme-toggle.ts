// The library header's chrome-scheme toggle (013 WI-13; C13.08 / C13.33 / C13.09).
//
// Same state as the settings page (@shared/scheme): mounting only reads and labels, it never
// writes, so an absent key stays absent until the user chooses. Each click steps
// system -> light -> dark -> system and applies it. The reader's paper axis
// (`data-reading-theme`) is not this control's business.
import { applyScheme, nextScheme, readScheme, type Scheme } from "@shared/scheme";

const LABEL: Readonly<Record<Scheme, string>> = {
  system: "界面明暗：跟随系统",
  light: "界面明暗：浅色",
  dark: "界面明暗：深色",
};

function paint(button: HTMLButtonElement, scheme: Scheme): void {
  button.setAttribute("aria-label", LABEL[scheme]);
  button.title = LABEL[scheme];
  button.dataset.scheme = scheme;
}

export function mountThemeToggle(button: HTMLButtonElement, root: HTMLElement, storage: Storage | null): void {
  // Held here, not re-read per click: with unusable storage the cycle must still advance.
  let current = readScheme(storage);
  paint(button, current);
  button.addEventListener("click", () => {
    current = nextScheme(current);
    applyScheme(current, root, storage);
    paint(button, current);
  });
}

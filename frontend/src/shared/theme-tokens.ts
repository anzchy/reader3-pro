// 013 WI-10: the Tier 2 theme tables (spec §3.3). The ONE definition of the two theme
// axes; frontend/theme-plugin.ts renders them into the built stylesheet.
//
//   CHROME_THEMES   data-theme on <html>: absent = follow the OS, "light", "dark".
//                   `light` goes on :root; `dark` is rendered once and placed under both
//                   the OS-dark media query and :root[data-theme="dark"] (decision D6).
//   READING_THEMES  data-reading-theme on <html>, scoped to .reader-shell. `auto` is null:
//                   it has NO rule, so the reader inherits the chrome's page-* / hl-*.
//                   The four papers are absolute -- identical under either chrome.
//
// The two axes share exactly ALLOWED_SHARED: the reading tokens whose `auto` value the
// chrome supplies (spec §3.3 rule 3). Every block restates hl-*-rgb AND the derived
// hl-*: a custom property substitutes var() on the element that declares it, so a
// derivation written once on :root would not follow a paper's triplet (spec §3.3 note).
//
// Values reference Tier 1 (`--p-*`, frontend/src/styles/tokens.css) where the spec does;
// literals are the spec's own literals. This file and tokens.css are the only places a
// `--p-*` name may appear.
//
// The type aliases are file-local on purpose: the module's runtime surface is exactly the
// three tables (theme-tokens-shape.test.ts pins it), and the Node type-stripped import in
// the packaging test needs this file to import nothing.

type TokenName = `--r3-${string}`;
type Declarations = Readonly<Record<TokenName, string>>;

// Literal keys on purpose: the WI-7 colour-set check greps `--r3-hl-<colour>-rgb:` here.
/** hl-*-rgb from the light Tier 1 triplets, plus the derived hl-*, restated per block. */
const HL_LIGHT: Declarations = {
  "--r3-hl-yellow-rgb": "var(--p-hl-yellow-rgb)",
  "--r3-hl-green-rgb": "var(--p-hl-green-rgb)",
  "--r3-hl-pink-rgb": "var(--p-hl-pink-rgb)",
  "--r3-hl-blue-rgb": "var(--p-hl-blue-rgb)",
  "--r3-hl-yellow": "rgb(var(--r3-hl-yellow-rgb))",
  "--r3-hl-green": "rgb(var(--r3-hl-green-rgb))",
  "--r3-hl-pink": "rgb(var(--r3-hl-pink-rgb))",
  "--r3-hl-blue": "rgb(var(--r3-hl-blue-rgb))",
};

/** The same names from the dark (`-dk`) Tier 1 triplets. */
const HL_DARK: Declarations = {
  "--r3-hl-yellow-rgb": "var(--p-hl-yellow-dk-rgb)",
  "--r3-hl-green-rgb": "var(--p-hl-green-dk-rgb)",
  "--r3-hl-pink-rgb": "var(--p-hl-pink-dk-rgb)",
  "--r3-hl-blue-rgb": "var(--p-hl-blue-dk-rgb)",
  "--r3-hl-yellow": "rgb(var(--r3-hl-yellow-rgb))",
  "--r3-hl-green": "rgb(var(--r3-hl-green-rgb))",
  "--r3-hl-pink": "rgb(var(--r3-hl-pink-rgb))",
  "--r3-hl-blue": "rgb(var(--r3-hl-blue-rgb))",
};

function page(bg: string, ink: string, quiet: string): Declarations {
  return { "--r3-page-bg": bg, "--r3-page-ink": ink, "--r3-page-quiet": quiet };
}

export const CHROME_THEMES: Readonly<Record<"light" | "dark", Declarations>> = {
  light: {
    "--r3-bg": "var(--p-gray-100)",
    "--r3-surface": "var(--p-gray-0)",
    "--r3-surface-raised": "var(--p-gray-0)",
    "--r3-surface-sunken": "var(--p-gray-50)",
    "--r3-surface-hover": "var(--p-gray-200)",
    "--r3-text": "var(--p-gray-800)",
    "--r3-text-muted": "var(--p-gray-600)",
    "--r3-text-subtle": "var(--p-gray-550)",
    "--r3-text-disabled": "var(--p-gray-400)",
    "--r3-text-on-accent": "var(--p-gray-0)",
    "--r3-border": "var(--p-gray-300)",
    "--r3-border-subtle": "#f0f0f0",
    "--r3-border-strong": "var(--p-gray-400)",
    "--r3-accent": "var(--p-blue-500)",
    "--r3-accent-hover": "var(--p-blue-600)",
    "--r3-accent-subtle": "var(--p-blue-50)",
    "--r3-focus-ring": "var(--p-blue-500)",
    "--r3-success": "var(--p-green-700)",
    "--r3-warning": "var(--p-amber-700)",
    "--r3-error": "var(--p-red-700)",
    "--r3-info": "var(--p-cyan-700)",
    "--r3-success-subtle": "var(--p-green-100)",
    "--r3-warning-subtle": "var(--p-amber-100)",
    "--r3-error-subtle": "var(--p-red-100)",
    "--r3-info-subtle": "var(--p-cyan-100)",
    "--r3-search-hit": "#fde68a",
    ...page("#ffffff", "#1f2937", "#64748b"),
    ...HL_LIGHT,
    "--r3-shadow-sm": "0 1px 3px rgb(0 0 0 / .05)",
    "--r3-shadow-md": "0 2px 10px rgb(0 0 0 / .05)",
    "--r3-shadow-lg": "0 4px 20px rgb(0 0 0 / .10)",
  },
  dark: {
    "--r3-bg": "#0b1220",
    "--r3-surface": "#131c2e",
    "--r3-surface-raised": "#1c2740",
    "--r3-surface-sunken": "#182335",
    "--r3-surface-hover": "#182335",
    "--r3-text": "#e2e8f0",
    "--r3-text-muted": "#94a3b8",
    "--r3-text-subtle": "#7a8aa2",
    "--r3-text-disabled": "#475569",
    "--r3-border": "#263349",
    "--r3-border-subtle": "#1c2740",
    "--r3-border-strong": "#35476a",
    "--r3-accent": "var(--p-blue-400)",
    "--r3-accent-subtle": "var(--p-blue-950)",
    "--r3-success": "var(--p-green-400)",
    "--r3-warning": "var(--p-amber-400)",
    "--r3-error": "var(--p-red-400)",
    "--r3-info": "var(--p-cyan-400)",
    "--r3-success-subtle": "var(--p-green-950)",
    "--r3-warning-subtle": "var(--p-amber-950)",
    "--r3-error-subtle": "var(--p-red-950)",
    "--r3-info-subtle": "var(--p-cyan-950)",
    "--r3-search-hit": "#7c5f12",
    ...page("#131c2e", "#dbe3ef", "#93a3bb"),
    ...HL_DARK,
    "--r3-shadow-sm": "0 1px 3px rgb(0 0 0 / .4)",
    "--r3-shadow-md": "0 2px 10px rgb(0 0 0 / .4)",
    "--r3-shadow-lg": "0 4px 20px rgb(0 0 0 / .6)",
  },
};

export const READING_THEMES: Readonly<Record<"auto" | "paper" | "sepia" | "green" | "night", Declarations | null>> = {
  auto: null,
  paper: { ...page("var(--p-gray-0)", "#1f2937", "#64748b"), ...HL_LIGHT },
  sepia: { ...page("var(--p-paper-sepia)", "#4a3b28", "#7a6449"), ...HL_LIGHT },
  green: { ...page("var(--p-paper-green)", "#24382a", "#506856"), ...HL_LIGHT },
  night: { ...page("var(--p-paper-night)", "#c2ccdb", "#7e8ca3"), ...HL_DARK },
};

/** The only names both axes declare: the reading tokens `auto` takes from the chrome. */
export const ALLOWED_SHARED: readonly TokenName[] = [
  "--r3-page-bg",
  "--r3-page-ink",
  "--r3-page-quiet",
  ...(Object.keys(HL_LIGHT) as TokenName[]),
];

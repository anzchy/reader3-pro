// 013 WI-10: the one import that puts the token layer on a page. Tier 1 palette and the
// theme-independent scales (tokens.css), then the plugin-generated colour tokens
// (light :root, the two dark rules, the four reading papers). Every entry imports this
// before its own stylesheet, so page CSS can only ever reference --r3-* names.
import "../styles/tokens.css";
import "virtual:r3-theme.css";

// ESLint for the TS frontend (013 WI-11 acceptance 1, ET-10). Deliberately minimal: the only
// rule is `no-console`; WI-14 extends this file (commands.ts DOM ban, ET-13), it does not
// start a second one.
//
//   * console.log is allowed nowhere in frontend/src. warn / error are allowed everywhere.
//   * shared/debug.ts is the one sanctioned sink for diagnostics and may also use info / debug.
//   * Inline `eslint-disable` comments are switched off, so no file can opt itself out; the
//     debug.ts grant lives here, visibly, instead of in a comment.
import tseslint from "typescript-eslint";

const WARN_AND_ERROR = ["warn", "error"];

export default [
  {
    files: ["frontend/src/**/*.ts"],
    languageOptions: { parser: tseslint.parser },
    linterOptions: { noInlineConfig: true, reportUnusedDisableDirectives: "off" },
    rules: { "no-console": ["error", { allow: WARN_AND_ERROR }] },
  },
  {
    files: ["frontend/src/shared/debug.ts"],
    rules: { "no-console": ["error", { allow: [...WARN_AND_ERROR, "info", "debug"] }] },
  },
];

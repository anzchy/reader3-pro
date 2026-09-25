#!/usr/bin/env node
// 013 WI-9 验收 11（§9.3）：token 硬编码 lint ＋ 指纹 ratchet。
//
// stylelint ＋ stylelint-declaration-strict-value ＋ postcss-html 扫：
//   * frontend/src/**/*.css
//   * src/reader3_app/web/templates/*.html（<style> 块与 style= 属性）
//   * src/reader3_app/web/static/**/*.css（不含 dist/、vendor/）
// 再加一条 `r3/token-namespace`：var() 只许引用 `--r3-*`（命名空间是白名单，不是黑名单）。
//
// 每条违规折成指纹 `文件:上下文:属性`——上下文 = at-rule 链 ＋ 规则选择器（空白归一），
// style= 属性记 `[style]`；**不含行号**，挪行不改指纹。与 scripts/hardcode_baseline.json
// （`{文件: ["上下文:属性", ...]}`，键必须是具体文件路径）比较：新增失败，过期（已修掉却
// 还登记着）也失败——登记表只能跟着修复一起减。增长另由 check_allowlist_monotone.py 把关。
//
// 抑制一律不认，且一律报出：本脚本用内联 config（不读任何 stylelint 配置文件、不读
// .stylelintignore）、`ignoreDisables: true`，所以 stylelint-disable 注释、ignoreFiles、
// overrides、.stylelintignore、package.json 的 stylelint 键、带通配的登记键都既无效又失败。
//
// 用法：node scripts/lint_hardcode.mjs [--root DIR] [--json] [--update-baseline]
//   --json             只打印 {new, stale, suppressions, fingerprints, errors}
//   --update-baseline  登记表存在时写入 实测 ∩ 现有（只减）；不存在时写入实测（首次建立）
//
// 不在本 lint 范围内（归属已定）：TS 里写样式（WI-14 的 ESLint 规则）；transition 简写
// （§9.3 注 3，v1 之后）；Tier 1 调色板 / reset 文件豁免（WI-10 建这两个文件时登记进
// EXEMPT_FILES）。

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import stylelint from "stylelint";
import strictValue from "stylelint-declaration-strict-value";
import postcssHtml from "postcss-html";

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BASELINE_REL = "scripts/hardcode_baseline.json";
const TEMPLATES_REL = "src/reader3_app/web/templates";
const STATIC_REL = "src/reader3_app/web/static";
const STATIC_EXCLUDE = new Set(["dist", "vendor"]);

/** §9.3 的豁免文件（Tier 1 调色板、reset）。WI-10 登记 Tier 1 定义处 tokens.css——它就是
 *  字面量与 `--p-*` 的唯一合法出处。reset 文件尚未建立，建时再登记。 */
export const EXEMPT_FILES = ["frontend/src/styles/tokens.css"];

const STRICT_PROPERTIES = [
  "z-index",
  "font-size",
  "transition-duration",
  "/^padding/",
  "/^margin/",
  "gap",
  "row-gap",
  "column-gap",
  "/^border(-(top|bottom|start|end)-(left|right|start|end))?-radius$/",
  "height",
  "min-height",
  "width",
  "min-width",
  "line-height",
  "opacity",
];

// ---------------------------------------------------------------------------
// r3/token-namespace
// ---------------------------------------------------------------------------
const NS_RULE = "r3/token-namespace";
const nsMessages = stylelint.utils.ruleMessages(NS_RULE, {
  rejected: (name) => `var(${name}) 不在 --r3-* 命名空间里`,
});
const nsRule = (primary) => (root, result) => {
  if (!primary) return;
  root.walkDecls((decl) => {
    for (const m of decl.value.matchAll(/var\(\s*(--[A-Za-z0-9_-]+)/g)) {
      if (!m[1].startsWith("--r3-")) {
        stylelint.utils.report({ ruleName: NS_RULE, result, node: decl, message: nsMessages.rejected(m[1]), word: m[1] });
      }
    }
  });
};
nsRule.ruleName = NS_RULE;
nsRule.messages = nsMessages;
const namespacePlugin = stylelint.createPlugin(NS_RULE, nsRule);

const CONFIG = {
  plugins: [strictValue, namespacePlugin],
  rules: {
    "color-no-hex": true,
    "function-disallowed-list": ["rgb", "rgba", "hsl", "hsla"],
    "scale-unlimited/declaration-strict-value": [
      STRICT_PROPERTIES,
      {
        ignoreFunctions: false,
        ignoreValues: {
          "": ["0", "100%", "50%", "/^[^0-9]*$/"],
          opacity: ["0", "1"],
        },
      },
    ],
    [NS_RULE]: true,
  },
};

// ---------------------------------------------------------------------------
// file sets
// ---------------------------------------------------------------------------
function walk(dir, accept, skipDir = () => false) {
  const out = [];
  if (!fs.existsSync(dir)) return out;
  for (const ent of fs.readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) {
      if (!skipDir(ent.name, full)) out.push(...walk(full, accept, skipDir));
    } else if (ent.isFile() && accept(ent.name)) {
      out.push(full);
    }
  }
  return out;
}

const rel = (root, p) => path.relative(root, p).split(path.sep).join("/");

function lintTargets(root) {
  const files = [
    ...walk(path.join(root, "frontend/src"), (n) => n.endsWith(".css")),
    ...walk(path.join(root, TEMPLATES_REL), (n) => n.endsWith(".html"), () => true),
    ...walk(path.join(root, STATIC_REL), (n) => n.endsWith(".css"), (name, full) =>
      STATIC_EXCLUDE.has(name) && path.dirname(full) === path.join(root, STATIC_REL)),
  ];
  return files.filter((f) => !EXEMPT_FILES.includes(rel(root, f)));
}

function suppressionTargets(root) {
  const src = /\.(css|ts|tsx|js|mjs|cjs|html)$/;
  return [
    ...walk(path.join(root, "frontend/src"), (n) => src.test(n)),
    ...walk(path.join(root, TEMPLATES_REL), (n) => n.endsWith(".html"), () => true),
    ...walk(path.join(root, STATIC_REL), (n) => n.endsWith(".css"), (name, full) =>
      STATIC_EXCLUDE.has(name) && path.dirname(full) === path.join(root, STATIC_REL)),
  ];
}

// ---------------------------------------------------------------------------
// fingerprints
// ---------------------------------------------------------------------------
const norm = (s) => s.replace(/\s+/g, " ").trim();

function context(decl, isHtml) {
  const parts = [];
  let node = decl.parent;
  while (node && (node.type === "rule" || node.type === "atrule")) {
    parts.unshift(node.type === "rule" ? norm(node.selector) : norm(`@${node.name} ${node.params}`));
    node = node.parent;
  }
  if (parts.length === 0) return isHtml ? "[style]" : "(top-level)";
  return parts.join(" ");
}

const before = (a, b) => a.line < b.line || (a.line === b.line && a.column <= b.column);

function declAt(decls, w) {
  const point = { line: w.line, column: w.column };
  let best = null;
  for (const d of decls) {
    const s = d.source?.start;
    const e = d.source?.end;
    if (!s || !e) continue;
    if (before(s, point) && before(point, { line: e.line, column: e.column + 1 })) {
      if (!best || before(best.source.start, s)) best = d;
    }
  }
  return best;
}

async function measure(root) {
  const fingerprints = new Set();
  const errors = [];
  for (const file of lintTargets(root)) {
    const r = rel(root, file);
    const isHtml = file.endsWith(".html");
    const code = fs.readFileSync(file, "utf8");
    // 故意不传 codeFilename / configFile：不走任何按路径的忽略，也不读任何配置文件。
    const out = await stylelint.lint({
      code,
      config: CONFIG,
      customSyntax: isHtml ? postcssHtml : undefined,
      ignoreDisables: true,
    });
    const res = out.results[0];
    for (const w of res.invalidOptionWarnings ?? []) errors.push(`${r}: 规则配置无效：${w.text}`);
    for (const w of res.parseErrors ?? []) errors.push(`${r}: 解析失败：${w.text}`);
    const decls = [];
    res._postcssResult.root.walkDecls((d) => decls.push(d));
    for (const w of res.warnings) {
      if (w.rule === "CssSyntaxError") {
        errors.push(`${r}:${w.line}: 解析失败：${w.text}`);
        continue;
      }
      const d = declAt(decls, w);
      if (!d) {
        errors.push(`${r}:${w.line}:${w.column}: 找不到对应声明（${w.rule}）`);
        continue;
      }
      fingerprints.add(`${r}:${context(d, isHtml)}:${d.prop}`);
    }
  }
  return { fingerprints: [...fingerprints].sort(), errors };
}

// ---------------------------------------------------------------------------
// suppression scan
// ---------------------------------------------------------------------------
const CONFIG_NAMES = [
  ".stylelintrc",
  ".stylelintrc.json",
  ".stylelintrc.yaml",
  ".stylelintrc.yml",
  ".stylelintrc.js",
  ".stylelintrc.cjs",
  ".stylelintrc.mjs",
  "stylelint.config.js",
  "stylelint.config.cjs",
  "stylelint.config.mjs",
  "stylelint.config.ts",
];
const SUPPRESSING_KEYS = ["ignoreFiles", "overrides", "ignoreDisables", "defaultSeverity"];

function scanSuppressions(root, baseline) {
  const found = [];
  for (const file of suppressionTargets(root)) {
    const lines = fs.readFileSync(file, "utf8").split("\n");
    lines.forEach((line, i) => {
      if (line.includes("stylelint-disable") || line.includes("stylelint-enable")) {
        found.push(`${rel(root, file)}:${i + 1}: stylelint-disable 注释（本 lint 以 ignoreDisables 运行，注释无效且不许出现）`);
      }
    });
  }
  for (const dir of ["", "frontend"]) {
    for (const name of CONFIG_NAMES) {
      const p = path.join(root, dir, name);
      if (!fs.existsSync(p)) continue;
      const text = fs.readFileSync(p, "utf8");
      for (const key of SUPPRESSING_KEYS) {
        if (text.includes(key)) found.push(`${rel(root, p)}: ${key}（stylelint 配置里的抑制面；本 lint 不读它，也不许它存在）`);
      }
    }
    const ignore = path.join(root, dir, ".stylelintignore");
    if (fs.existsSync(ignore)) {
      const live = fs.readFileSync(ignore, "utf8").split("\n").filter((l) => l.trim() && !l.trim().startsWith("#"));
      if (live.length) found.push(`${rel(root, ignore)}: ${live.length} 条忽略（本 lint 不读它，也不许它存在）`);
    }
    const pkgPath = path.join(root, dir, "package.json");
    if (fs.existsSync(pkgPath)) {
      try {
        const cfg = JSON.parse(fs.readFileSync(pkgPath, "utf8")).stylelint;
        if (cfg && typeof cfg === "object") {
          for (const key of SUPPRESSING_KEYS) {
            if (key in cfg) found.push(`${rel(root, pkgPath)}: stylelint.${key}（抑制面）`);
          }
        }
      } catch {
        // 解析不了的 package.json 不归本 lint 管
      }
    }
  }
  for (const key of Object.keys(baseline)) {
    if (/[*?[\]:]/.test(key)) found.push(`${BASELINE_REL}: 键 ${JSON.stringify(key)} 不是具体文件（通配/冒号登记等于整片豁免）`);
  }
  return found;
}

// ---------------------------------------------------------------------------
// baseline
// ---------------------------------------------------------------------------
function readBaseline(root) {
  const p = path.join(root, BASELINE_REL);
  if (!fs.existsSync(p)) return { exists: false, data: {} };
  return { exists: true, data: JSON.parse(fs.readFileSync(p, "utf8")) };
}

function flatten(data) {
  const out = new Set();
  for (const [file, entries] of Object.entries(data)) {
    for (const e of Array.isArray(entries) ? entries : []) out.add(`${file}:${e}`);
  }
  return out;
}

function toBaseline(fingerprints) {
  const data = {};
  for (const f of fingerprints) {
    const i = f.indexOf(":");
    (data[f.slice(0, i)] ??= []).push(f.slice(i + 1));
  }
  const sorted = {};
  for (const k of Object.keys(data).sort()) sorted[k] = [...new Set(data[k])].sort();
  return sorted;
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------
async function main(argv) {
  let root = REPO_ROOT;
  let json = false;
  let update = false;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--root") root = path.resolve(argv[++i]);
    else if (a === "--json") json = true;
    else if (a === "--update-baseline") update = true;
    else {
      process.stderr.write(`lint_hardcode: 未知参数 ${a}\n`);
      return 2;
    }
  }

  const { fingerprints, errors } = await measure(root);
  let { exists, data } = readBaseline(root);
  if (update) {
    const measured = new Set(fingerprints);
    const keep = exists ? [...flatten(data)].filter((f) => measured.has(f)) : fingerprints;
    data = toBaseline(keep);
    fs.mkdirSync(path.dirname(path.join(root, BASELINE_REL)), { recursive: true });
    fs.writeFileSync(path.join(root, BASELINE_REL), JSON.stringify(data, null, 2) + "\n");
  }

  const baseline = flatten(data);
  const measured = new Set(fingerprints);
  const report = {
    new: fingerprints.filter((f) => !baseline.has(f)),
    stale: [...baseline].filter((f) => !measured.has(f)).sort(),
    suppressions: scanSuppressions(root, data),
    fingerprints,
    errors,
  };
  const failed = report.new.length || report.stale.length || report.suppressions.length || errors.length;

  if (json) {
    process.stdout.write(JSON.stringify(report, null, 2) + "\n");
  } else {
    const files = new Set(fingerprints.map((f) => f.slice(0, f.indexOf(":"))));
    process.stdout.write(`指纹 ${fingerprints.length} 条，分布在 ${files.size} 个文件；登记 ${baseline.size} 条。\n`);
    const section = (title, items) => {
      if (!items.length) return;
      process.stdout.write(`${title}（${items.length} 条）：\n`);
      for (const x of items) process.stdout.write(`  ${x}\n`);
    };
    section("新增硬编码——改用 --r3-* token", report.new);
    section("过期登记——已修掉，请从 scripts/hardcode_baseline.json 删除（或 --update-baseline）", report.stale);
    section("抑制面——一律不许", report.suppressions);
    section("运行错误", errors);
    if (!failed) process.stdout.write("硬编码 ratchet 通过。\n");
  }
  return failed ? 1 : 0;
}

process.exitCode = await main(process.argv.slice(2));

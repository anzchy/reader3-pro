"""023 WI-2（009 欠账 #66）：always-dump 的 fetch 台账要活过导航。

`_FETCH_LEDGER` 是按文档注入的 init script，`window.__r3FetchLog` 随每次导航 / 重载一起死掉。
w5a0 的一轮 always-dump 里只剩最后一个文档的两条 GET，前面的 POST、POST、DELETE 全丢了。

钉住的方案（协调者裁定）：`window.__r3FetchLog` 不变；另把台账镜像进 sessionStorage 的
唯一键 `__r3_diag_fetch_ledger`，值是段数组 `[{doc, url, entries}]`。每个顶层文档在 init
时追加自己的一段（哪怕从不 fetch），在 send 与 settle 时读-改-写、**按 doc id**（不是 URL）
替换自己那一段；从不 clear / key / length / 碰别的键；所有存储访问包 try/catch；只有顶层帧写。

矩阵：`.claude/tdd-guardian/tests-20261001-124913.md` §「_FETCH_LEDGER」N1–N9、NP1–NP2，
§「pytest_runtest_makereport + _r3_diag_capture」P1–P3。

**Node 缺失是失败，不是 skip**（`tests/fixtures/frontend_host.py` 的先例）。jsdom 与
fast-check 取仓库 `node_modules`。注入脚本经 JSON 文件原样传给 Node，从不在这里重打一遍。

P2 用子解释器跑真 pytest，不用 `pytester`：`pytester` 要么在 rootdir conftest 写
`pytest_plugins`（`tests/conftest.py` 是冻结路径），要么动 `addopts`——理由与
`tests/unit/test_egress_backstop_subprocess.py` 文首相同。
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from playwright.sync_api import Error as PlaywrightError

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tests" / "fixtures"))
import frontend_host  # noqa: E402

_DUMP_PATH = REPO_ROOT / "scripts" / "e2e_diag_dump.py"
_spec = importlib.util.spec_from_file_location("reader3_e2e_diag_dump_fetch_ledger_under_test", _DUMP_PATH)
assert _spec and _spec.loader, f"无法按路径加载 {_DUMP_PATH}"
diag = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = diag
_spec.loader.exec_module(diag)

KEY = "__r3_diag_fetch_ledger"
U0 = "http://127.0.0.1:1/read/b/0"
U1 = "http://127.0.0.1:1/read/b/1"
NODE_TIMEOUT_S = 60
CHILD_TIMEOUT_S = 60


# --------------------------------------------------------------------------
# Node harness
# --------------------------------------------------------------------------

_HARNESS = r"""
import { createRequire } from "node:module";
import fs from "node:fs";
import vm from "node:vm";

const input = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const require = createRequire(input.repoRoot + "/package.json");
const { JSDOM } = require("jsdom");
const fc = require("fast-check");
const SCRIPT = input.script;
const READBACK = input.readback;
const KEY = "__r3_diag_fetch_ledger";
const U0 = "http://127.0.0.1:1/read/b/0";
const U1 = "http://127.0.0.1:1/read/b/1";

const flush = () => new Promise((r) => setImmediate(r));
const plain = (v) => (v === undefined ? null : JSON.parse(JSON.stringify(v)));

// ---- real jsdom Storage wrapped in a recorder -------------------------------
function makeStorage(opts = {}) {
  const dom = new JSDOM("", { url: "http://127.0.0.1:1/", storageQuota: opts.quota ?? 5000000 });
  const target = dom.window.sessionStorage;
  const access = [];
  const calls = [];
  let fail = null;
  const proxy = new Proxy(target, {
    get(t, prop) {
      access.push(String(prop));
      const v = Reflect.get(t, prop, t);
      if (typeof v === "function") {
        return (...a) => {
          calls.push({ name: String(prop), key: a[0] });
          if (fail && fail(String(prop))) throw new dom.window.DOMException("injected", "UnknownError");
          return v.apply(t, a);
        };
      }
      return v;
    },
    set(t, p, v) { access.push("set:" + String(p)); return Reflect.set(t, p, v, t); },
    has(t, p) { access.push("has:" + String(p)); return Reflect.has(t, p); },
    ownKeys(t) { access.push("ownKeys"); return Reflect.ownKeys(t); },
    getOwnPropertyDescriptor(t, p) { access.push("gopd:" + String(p)); return Reflect.getOwnPropertyDescriptor(t, p); },
    deleteProperty(t, p) { access.push("delete:" + String(p)); return Reflect.deleteProperty(t, p); },
    defineProperty(t, p, d) { access.push("define:" + String(p)); return Reflect.defineProperty(t, p, d); },
  });
  const dump = () => {
    const out = {};
    for (let i = 0; i < target.length; i++) { const k = target.key(i); out[k] = target.getItem(k); }
    return out;
  };
  return { dom, target, proxy, access, calls, dump, setFail: (f) => { fail = f; } };
}

// ---- one tab: shared clock, shared network stub, shared storage --------------
function makeTab(opts = {}) {
  let tick = 0;
  const clock = () => 1000 + 10 * tick++;
  const net = { calls: [], pending: [] };
  net.fetch = function (...args) {
    let resolve, reject;
    const p = new Promise((a, b) => { resolve = a; reject = b; });
    const d = { args, resolve, reject, p };
    net.calls.push(d);
    return p;
  };
  const storage = makeStorage(opts);
  return { clock, net, storage, docs: [] };
}

function makeDoc(tab, href, opts = {}) {
  const ctx = vm.createContext({});
  const getter = opts.getter || (() => tab.storage.proxy);
  ctx.__clock = tab.clock;
  ctx.__fetch = tab.net.fetch;
  ctx.__href = href;
  ctx.__ss = getter;
  vm.runInContext(
    "globalThis.window = globalThis; globalThis.self = globalThis;" +
    "Date.now = __clock; globalThis.fetch = __fetch; globalThis.location = { href: __href };" +
    "Object.defineProperty(globalThis, 'sessionStorage', { get: __ss, configurable: true });",
    ctx,
  );
  if (opts.top === false) ctx.__topObj = {};
  vm.runInContext(opts.top === false ? "globalThis.top = __topObj;" : "globalThis.top = globalThis;", ctx);
  const doc = { ctx, href };
  doc.inject = () => vm.runInContext(SCRIPT, ctx);
  doc.fetch = (...a) => ctx.fetch(...a);
  doc.log = () => plain(ctx.__r3FetchLog);
  tab.docs.push(doc);
  return doc;
}

function lastCall(tab) { return tab.net.calls[tab.net.calls.length - 1]; }
function ledger(tab) {
  const raw = tab.storage.target.getItem(KEY);
  let parsed = null;
  try { parsed = JSON.parse(raw); } catch (e) { parsed = "__UNPARSEABLE__"; }
  return { raw, parsed };
}

// A notes fetch that settles right away with {status}.
async function doFetch(tab, doc, args, status) {
  const p = doc.fetch(...args);
  const d = lastCall(tab);
  const R = { status };
  d.resolve(R);
  const v = await p;
  await flush();
  return v === R;
}

// ---- scenarios ---------------------------------------------------------------
async function runN1(tab, pageWrite) {
  const pw = pageWrite || (() => {});
  const d0 = makeDoc(tab, U0); d0.inject();
  pw();
  await doFetch(tab, d0, ["/api/notes/b/0", { method: "POST" }], 201);
  pw();
  await doFetch(tab, d0, ["/api/notes/b/0", { method: "POST" }], 201);
  pw();
  await doFetch(tab, d0, ["/api/notes/b/0/x", { method: "DELETE" }], 204);
  pw();
  const d1 = makeDoc(tab, U1); d1.inject();
  pw();
  await doFetch(tab, d1, ["/api/notes/b/1"], 200);
  pw();
  return { d0, d1 };
}

const S = {};

S.N1 = async () => {
  const tab = makeTab();
  const { d1 } = await runN1(tab);
  return { ...ledger(tab), log1: d1.log() };
};

S.N2a = async () => {
  const tab = makeTab();
  const d0 = makeDoc(tab, U0); d0.inject();
  d0.fetch("/api/notes/b/0", { method: "POST" });
  await flush();
  const d1 = makeDoc(tab, U1); d1.inject();
  await flush();
  return ledger(tab);
};

S.N2b = async () => {
  const tab = makeTab();
  const d0 = makeDoc(tab, U0); d0.inject();
  const p0 = d0.fetch("/api/notes/b/0", { method: "POST" });
  const pend = lastCall(tab);
  await flush();
  const d1 = makeDoc(tab, U1); d1.inject();
  await doFetch(tab, d1, ["/api/notes/b/1"], 200);
  pend.resolve({ status: 201 });
  await p0;
  await flush();
  return ledger(tab);
};

S.N3 = async () => {
  const tab = makeTab();
  const t = tab.storage.target;
  t.setItem("r3_app", "keep\u0000me ✓");
  t.setItem("other", "{\"x\":1}");
  t.setItem("__r3_diag_fetch_ledger_x", "decoy");
  await runN1(tab, () => t.setItem("r3_app", "v2"));
  return { final: tab.storage.dump(), access: tab.storage.access, calls: tab.storage.calls };
};

S.N4 = async () => {
  const tab = makeTab();
  const d0 = makeDoc(tab, U0); d0.inject(); d0.inject();
  await doFetch(tab, d0, ["/api/notes/b/0", { method: "POST" }], 201);
  await doFetch(tab, d0, ["/api/notes/b/0", { method: "POST" }], 201);
  const d1 = makeDoc(tab, U1); d1.inject(); d1.inject();
  await doFetch(tab, d1, ["/api/notes/b/1"], 200);
  return { netCalls: tab.net.calls.length, len0: d0.log().length, len1: d1.log().length, ...ledger(tab) };
};

S.N5a = async () => {
  const tab = makeTab({ quota: 1 });
  const d0 = makeDoc(tab, U0);
  let evalThrew = null;
  try { d0.inject(); } catch (e) { evalThrew = String(e); }
  const R = { status: 201 };
  const E = new Error("net down");
  const p1 = d0.fetch("/api/notes/b/0", { method: "POST" });
  lastCall(tab).resolve(R);
  const v1 = await p1;
  await flush();
  const p2 = d0.fetch("/api/notes/b/0", { method: "POST" });
  lastCall(tab).reject(E);
  let rejectedSame = false, resolvedInstead = false;
  try { await p2; resolvedInstead = true; } catch (e) { rejectedSame = e === E; }
  await flush();
  return { evalThrew, firstSame: v1 === R, rejectedSame, resolvedInstead, log: d0.log(), stored: tab.storage.dump(), errString: String(E) };
};

S.N5b = async () => {
  const out = {};
  for (const seed of ["{not json", "null", "{\"a\":1}", "[1,2]"]) {
    const tab = makeTab();
    tab.storage.target.setItem(KEY, seed);
    const d0 = makeDoc(tab, U0);
    let evalThrew = null;
    try { d0.inject(); } catch (e) { evalThrew = String(e); }
    let same = false;
    try { same = await doFetch(tab, d0, ["/api/notes/b/0", { method: "POST" }], 201); } catch (e) { same = "threw: " + String(e); }
    out[seed] = { evalThrew, same, logLen: (d0.log() || []).length, ...ledger(tab) };
  }
  return out;
};

S.N5c = async () => {
  const tab = makeTab();
  const d0 = makeDoc(tab, U0, { getter: () => { throw new DOMException("denied", "SecurityError"); } });
  let evalThrew = null;
  try { d0.inject(); } catch (e) { evalThrew = String(e); }
  let same = false;
  try { same = await doFetch(tab, d0, ["/api/notes/b/0", { method: "POST" }], 201); } catch (e) { same = "threw: " + String(e); }
  return { evalThrew, same, log: d0.log() };
};

S.N6 = async () => {
  const tab = makeTab();
  const d0 = makeDoc(tab, U0); d0.inject();
  await doFetch(tab, d0, ["/api/notes/b/0", { method: "POST" }], 201);
  const snap = tab.storage.target.getItem(KEY);
  const req = { url: "/api/library" };
  const init = { method: "POST" };
  const argSets = [["/read/b/book.epub"], [req], ["/api/search/b?q=x", init]];
  const results = [];
  for (const args of argSets) {
    const before = tab.net.calls.length;
    const p = d0.fetch(...args);
    const reached = tab.net.calls.length === before + 1;
    const d = lastCall(tab);
    const R = { status: 200 };
    d.resolve(R);
    const v = await p;
    await flush();
    results.push({
      reached,
      same: v === R,
      argsSame: d.args.length === args.length && d.args.every((a, i) => a === args[i]),
    });
  }
  return { results, logLen: d0.log().length, snap, after: tab.storage.target.getItem(KEY) };
};

S.N7 = async () => {
  if (READBACK == null) return { skipped: "no read-back script located on the Python side" };
  const tab = makeTab();
  const { d1 } = await runN1(tab);
  const call = () => {
    try { return { value: plain(vm.runInContext("(" + READBACK + ")()", d1.ctx)) }; }
    catch (e) { return { threw: String(e) }; }
  };
  const stored = JSON.parse(tab.storage.target.getItem(KEY));
  const afterN1 = call();
  tab.storage.target.removeItem(KEY);
  const absent = call();
  tab.storage.target.setItem(KEY, "{not json");
  const corrupt = call();
  return { stored, afterN1, absent, corrupt };
};

S.N8 = async () => {
  const tab = makeTab();
  const d0 = makeDoc(tab, U0); d0.inject();
  await doFetch(tab, d0, ["/api/notes/b/0", { method: "POST" }], 201);
  const before = tab.storage.target.getItem(KEY);
  let getterHits = 0;
  const frame = makeDoc(tab, "http://127.0.0.1:1/epub/frame.xhtml", {
    top: false,
    getter: () => { getterHits++; return tab.storage.proxy; },
  });
  let evalThrew = null;
  try { frame.inject(); } catch (e) { evalThrew = String(e); }
  const same = await doFetch(tab, frame, ["/api/notes/b/0", { method: "POST" }], 201);
  return { evalThrew, same, getterHits, frameLog: frame.log(), before, after: tab.storage.target.getItem(KEY) };
};

S.N9 = async () => {
  const tab = makeTab();
  const d0 = makeDoc(tab, U0); d0.inject();
  await doFetch(tab, d0, ["/api/notes/b/0", { method: "POST" }], 201);
  const d1 = makeDoc(tab, U0); d1.inject();
  await doFetch(tab, d1, ["/api/notes/b/0"], 200);
  return ledger(tab);
};

// ---- properties ----------------------------------------------------------------
const HREFS = [U0, U1];
const FOREIGN = ["r3_app", "other"];
const METHODS = ["GET", "POST", "PUT", "DELETE"];
const STATUSES = [200, 201, 204, 404, 409, 500];

const stepArb = fc.oneof(
  { weight: 2, arbitrary: fc.record({ t: fc.constant("nav"), href: fc.nat(1), keep: fc.boolean() }) },
  { weight: 6, arbitrary: fc.record({
      t: fc.constant("notes"), target: fc.nat(3), method: fc.constantFrom(...METHODS),
      outcome: fc.oneof(
        fc.record({ k: fc.constant("resolve"), status: fc.constantFrom(...STATUSES) }),
        fc.record({ k: fc.constant("reject") }),
        fc.record({ k: fc.constant("pending") }),
      ),
    }) },
  { weight: 1, arbitrary: fc.record({ t: fc.constant("other"), target: fc.nat(3) }) },
  { weight: 2, arbitrary: fc.record({ t: fc.constant("settle"), target: fc.nat(3), i: fc.nat(5), ok: fc.boolean(), status: fc.constantFrom(...STATUSES) }) },
  { weight: 1, arbitrary: fc.record({ t: fc.constant("reinject"), target: fc.nat(3) }) },
  { weight: 1, arbitrary: fc.record({ t: fc.constant("app"), key: fc.constantFrom(...FOREIGN), value: fc.string({ maxLength: 6 }) }) },
);
const progArb = fc.record({ href0: fc.nat(1), steps: fc.array(stepArb, { maxLength: 30 }) });
const failArb = fc.record({
  bits: fc.array(fc.boolean(), { minLength: 1, maxLength: 16 }),
  getterThrows: fc.array(fc.boolean(), { minLength: 4, maxLength: 4 }),
});

// Pinned interleaving: doc1 inits while doc0 is alive, doc1 sends, then doc0 sends its first.
const PINNED = {
  href0: 0,
  steps: [
    { t: "nav", href: 1, keep: true },
    { t: "notes", target: 1, method: "POST", outcome: { k: "resolve", status: 201 } },
    { t: "notes", target: 0, method: "DELETE", outcome: { k: "pending" } },
    { t: "settle", target: 0, i: 0, ok: true, status: 204 },
  ],
};

async function execute(prog, failure) {
  const tab = makeTab();
  const t = tab.storage.target;
  const appModel = { r3_app: "seed-a", other: "seed-b" };
  for (const k of FOREIGN) t.setItem(k, appModel[k]);
  let bitI = 0;
  if (failure) tab.storage.setFail((name) => (name === "getItem" || name === "setItem") && failure.bits[bitI++ % failure.bits.length]);
  const problems = [];
  const model = [];   // per doc: { href, entries: [{method, url, state, status}] }
  let live = [];      // indices into model / tab.docs
  const create = (hi) => {
    const k = model.length;
    const throwing = failure && failure.getterThrows[k % 4];
    const doc = makeDoc(tab, HREFS[hi], throwing ? { getter: () => { throw new DOMException("denied", "SecurityError"); } } : {});
    try { doc.inject(); } catch (e) { problems.push("inject threw: " + String(e)); }
    doc.pend = [];
    model.push({ href: HREFS[hi], entries: [] });
    return k;
  };
  const watch = (p, expect, label) => p.then(
    (v) => { if (expect.kind !== "resolve" || v !== expect.obj) problems.push(label + ": resolved with a foreign value"); },
    (e) => { if (expect.kind !== "reject" || e !== expect.obj) problems.push(label + ": rejected with a foreign value"); },
  );
  live.push(create(prog.href0));
  for (const st of prog.steps) {
    if (st.t === "nav") {
      if (model.length >= 4) continue;
      const k = create(st.href);
      live = st.keep ? live.concat([k]).slice(-2) : [k];
    } else if (st.t === "app") {
      t.setItem(st.key, st.value); appModel[st.key] = st.value;
    } else {
      const k = live[st.target % live.length];
      const doc = tab.docs[k];
      if (st.t === "reinject") {
        try { doc.inject(); } catch (e) { problems.push("reinject threw: " + String(e)); }
      } else if (st.t === "other") {
        const p = doc.fetch("/read/b/book.epub");
        const R = { status: 200 };
        const w = watch(p, { kind: "resolve", obj: R }, "other");
        lastCall(tab).resolve(R);
        await w; await flush();
      } else if (st.t === "notes") {
        const url = "/api/notes/b/" + model[k].entries.length;
        const p = doc.fetch(url, { method: st.method });
        const d = lastCall(tab);
        const m = { method: st.method, url, state: "pending", status: null };
        model[k].entries.push(m);
        if (st.outcome.k === "resolve") {
          const R = { status: st.outcome.status };
          const w = watch(p, { kind: "resolve", obj: R }, "notes");
          d.resolve(R); m.state = "ok"; m.status = R.status;
          await w;
        } else if (st.outcome.k === "reject") {
          const E = new Error("boom");
          const w = watch(p, { kind: "reject", obj: E }, "notes");
          d.reject(E); m.state = "err";
          await w;
        } else {
          doc.pend.push({ d, p, m });
        }
        await flush();
      } else if (st.t === "settle") {
        if (doc.pend.length === 0) continue;
        const { d, p, m } = doc.pend.splice(st.i % doc.pend.length, 1)[0];
        if (st.ok) {
          const R = { status: st.status };
          const w = watch(p, { kind: "resolve", obj: R }, "settle");
          d.resolve(R); m.state = "ok"; m.status = R.status;
          await w;
        } else {
          const E = new Error("late boom");
          const w = watch(p, { kind: "reject", obj: E }, "settle");
          d.reject(E); m.state = "err";
          await w;
        }
        await flush();
      }
    }
  }
  return { tab, model, problems, appModel };
}

function entryMatches(e, m) {
  if (!e || e.method !== m.method || e.url !== m.url) return false;
  if (m.state === "pending") return e.settled === null && e.status === null && e.error === null;
  if (m.state === "ok") return e.settled !== null && e.status === m.status && e.error === null;
  return e.settled !== null && e.status === null && typeof e.error === "string";
}

function logMatches(log, entries) {
  return Array.isArray(log) && log.length === entries.length && log.every((e, i) => entryMatches(e, entries[i]));
}

function checkForeign(tab, appModel, problems) {
  for (const k of FOREIGN) {
    if (tab.storage.target.getItem(k) !== appModel[k]) problems.push("foreign key changed: " + k);
  }
}

async function np1Body(prog) {
  const { tab, model, problems, appModel } = await execute(prog, null);
  const raw = tab.storage.target.getItem(KEY);
  let led;
  try { led = JSON.parse(raw); } catch (e) { led = null; }
  if (!Array.isArray(led)) { problems.push("ledger not an array: " + raw); throw new Error(problems.join("\n")); }
  // 3. ordering
  if (led.length !== model.length) problems.push(`segments ${led.length} != documents ${model.length}`);
  if (JSON.stringify(led.map((s) => s.url)) !== JSON.stringify(model.map((m) => m.href))) problems.push("segment urls out of init order");
  if (new Set(led.map((s) => s.doc)).size !== led.length) problems.push("doc ids not distinct");
  // 1. conservation
  const total = led.reduce((n, s) => n + (s.entries || []).length, 0);
  const sent = model.reduce((n, m) => n + m.entries.length, 0);
  if (total !== sent) problems.push(`entries ${total} != notes fetches ${sent}`);
  model.forEach((m, k) => {
    const seg = led[k];
    if (!seg || !logMatches(seg.entries, m.entries)) problems.push(`segment ${k} != model ${JSON.stringify(m.entries)} got ${JSON.stringify(seg)}`);
    // 2. mirror: every document's segment == its in-page log
    if (seg && JSON.stringify(seg.entries) !== JSON.stringify(tab.docs[k].log())) problems.push(`segment ${k} != __r3FetchLog`);
    // 4. timestamps
    const es = (seg && seg.entries) || [];
    for (let i = 0; i < es.length; i++) {
      if (i > 0 && es[i].sent < es[i - 1].sent) problems.push(`segment ${k} sent decreases`);
      if (es[i].settled === null) {
        if (es[i].status !== null || es[i].error !== null) problems.push(`segment ${k} unsettled entry has outcome`);
      } else if (!(es[i].settled >= es[i].sent)) problems.push(`segment ${k} settled < sent`);
    }
  });
  // 5. frame
  checkForeign(tab, appModel, problems);
  const names = new Set(tab.storage.access);
  for (const n of names) if (n !== "getItem" && n !== "setItem") problems.push("storage access outside {getItem,setItem}: " + n);
  for (const c of tab.storage.calls) if (c.key !== KEY) problems.push("storage call on foreign key: " + c.key);
  if (problems.length) throw new Error(problems.join("\n"));
}

async function np2Body(prog, failure) {
  const { tab, model, problems, appModel } = await execute(prog, failure);
  model.forEach((m, k) => {
    if (!logMatches(tab.docs[k].log(), m.entries)) problems.push(`doc ${k} __r3FetchLog != model`);
  });
  checkForeign(tab, appModel, problems);
  if (problems.length) throw new Error(problems.join("\n"));
}

async function runProp(prop, examples) {
  const seed = (Date.now() ^ Math.floor(Math.random() * 0x7fffffff)) | 0;
  const r = await fc.check(prop, { numRuns: 200, seed, examples });
  return {
    ok: !r.failed,
    numRuns: r.numRuns,
    seed,
    counterexample: r.failed ? JSON.stringify(r.counterexample) : null,
    error: r.failed ? String(r.errorInstance || r.error) : null,
  };
}

S.NP1 = () => runProp(fc.asyncProperty(progArb, np1Body), [[PINNED]]);
S.NP2 = () => runProp(
  fc.asyncProperty(progArb, failArb, np2Body),
  [[PINNED, { bits: [true, false, true], getterThrows: [false, true, false, false] }]],
);

// ---- run everything; one scenario's crash never hides another's result --------
const out = {};
for (const name of input.scenarios) {
  try { out[name] = await S[name](); }
  catch (e) { out[name] = { harnessError: String((e && e.stack) || e) }; }
}
process.stdout.write("\n@@RESULT@@" + JSON.stringify(out) + "\n");
"""

SCENARIOS = ["N1", "N2a", "N2b", "N3", "N4", "N5a", "N5b", "N5c", "N6", "N7", "N8", "N9", "NP1", "NP2"]


# --------------------------------------------------------------------------
# Python-side fakes
# --------------------------------------------------------------------------

def _drive(item: Any, when: str, outcome: str) -> None:
    rep = SimpleNamespace(
        when=when,
        failed=outcome == "failed",
        passed=outcome == "passed",
        skipped=outcome == "skipped",
    )
    gen = diag.pytest_runtest_makereport(item, None)
    next(gen)
    with pytest.raises(StopIteration):
        gen.send(SimpleNamespace(get_result=lambda: rep))


class RecordingPage:
    """每次 evaluate 返回唯一哨兵 `{"__call": i}`，并记下脚本原文（N7 按行为定位读回脚本）。"""

    url = U1

    def __init__(self) -> None:
        self.scripts: List[str] = []

    def evaluate(self, script: str, *_args: Any) -> Any:
        self.scripts.append(script)
        return {"__call": len(self.scripts) - 1}


class FakeLedgerPage:
    """P1 的假页：按脚本内容区分 fetch / fetch_docs，并可对选中的键抛 PlaywrightError。"""

    url = U1

    def __init__(self, raising: frozenset) -> None:
        self.raising = raising
        self.n = 0
        self.index: Dict[str, int] = {}

    def evaluate(self, script: str, *_args: Any) -> Any:
        i = self.n
        self.n += 1
        if "__r3FetchLog" in script:
            key, value = "fetch", {"log": i}
        elif KEY in script:
            key, value = "fetch_docs", {"docs": i}
        else:
            return []
        self.index[key] = i
        if key in self.raising:
            raise PlaywrightError(f"boom-{key}")
        return value


def _locate_readback_script(tmp: Path) -> Optional[str]:
    """把 makereport 喂给 page.evaluate 的脚本里，结果落进 record["fetch_docs"] 的那一条找出来。"""
    page = RecordingPage()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(diag, "_OUT", tmp)
        mp.setenv("E2E_DIAG_ALWAYS", "1")
        _drive(SimpleNamespace(nodeid="tests/e2e/x.py::n7", funcargs={"page": page}), "call", "passed")
    files = sorted(tmp.glob("*.json"))
    if len(files) != 1:
        return None
    record = json.loads(files[0].read_text(encoding="utf-8"))
    sentinel = record.get("fetch_docs")
    if not isinstance(sentinel, dict) or "__call" not in sentinel:
        return None
    return page.scripts[sentinel["__call"]]


@pytest.fixture(scope="module")
def harness(tmp_path_factory: pytest.TempPathFactory) -> Dict[str, Any]:
    frontend_host.require_node_toolchain()
    work = tmp_path_factory.mktemp("fetch_ledger")
    readback = _locate_readback_script(work / "n7_dump")
    harness_path = work / "harness.mjs"
    harness_path.write_text(_HARNESS, encoding="utf-8")
    input_path = work / "input.json"
    input_path.write_text(
        json.dumps({
            "repoRoot": str(REPO_ROOT),
            "script": diag._FETCH_LEDGER,
            "readback": readback,
            "scenarios": SCENARIOS,
        }),
        encoding="utf-8",
    )
    proc = frontend_host.run(["node", str(harness_path), str(input_path)], cwd=REPO_ROOT, timeout=NODE_TIMEOUT_S)
    marker = "@@RESULT@@"
    if proc.returncode != 0 or marker not in proc.stdout:
        pytest.fail("node harness did not produce a result:\n" + frontend_host.describe(proc), pytrace=False)
    result = json.loads(proc.stdout.rsplit(marker, 1)[1])
    result["__readback__"] = readback
    return result


def _scenario(harness: Dict[str, Any], name: str) -> Dict[str, Any]:
    res = harness[name]
    assert "harnessError" not in res, f"{name} crashed inside the harness:\n{res['harnessError']}"
    return res


def _ledger(res: Dict[str, Any]) -> Any:
    raw = res["raw"]
    assert raw is not None, (
        f"sessionStorage[{KEY!r}] is null: nothing survived navigation (the #66 shape)"
    )
    try:
        ledger = json.loads(raw)
    except json.JSONDecodeError:
        ledger = None
    assert isinstance(ledger, list), f"sessionStorage[{KEY!r}] is not a JSON array: {raw!r}"
    return ledger


def _entry(method: str, url: str, sent: int, settled: Optional[int], status: Optional[int]) -> Dict[str, Any]:
    return {"method": method, "url": url, "sent": sent, "settled": settled, "status": status, "error": None}


# --------------------------------------------------------------------------
# N1–N9
# --------------------------------------------------------------------------

def test_n1_three_writes_in_doc0_survive_into_doc1s_view(harness: Dict[str, Any]) -> None:
    res = _scenario(harness, "N1")
    ledger = _ledger(res)
    assert isinstance(ledger, list) and len(ledger) == 2, f"expected 2 segments, got {ledger!r}"
    # 时钟模型：tab 共用一只钟，1000 起每次调用 +10；每个文档 init 取一次作 t0，每次 send、
    # 每次 settle 各取一次，记录的是相对 t0 的毫秒数。doc0：t0=1000，三次往返 1010..1060；
    # doc1：t0=1070，GET 1080 / 1090。
    assert ledger[0]["url"] == U0
    assert ledger[0]["entries"] == [
        _entry("POST", "/api/notes/b/0", 10, 20, 201),
        _entry("POST", "/api/notes/b/0", 30, 40, 201),
        _entry("DELETE", "/api/notes/b/0/x", 50, 60, 204),
    ]
    assert ledger[1]["url"] == U1
    assert ledger[1]["entries"] == [_entry("GET", "/api/notes/b/1", 10, 20, 200)]
    assert ledger[0]["doc"] != ledger[1]["doc"]
    assert set(ledger[0]) == {"doc", "url", "entries"}
    assert res["log1"] == ledger[1]["entries"] and len(res["log1"]) == 1


def test_n2a_in_flight_write_at_navigation_is_kept_unsettled(harness: Dict[str, Any]) -> None:
    ledger = _ledger(_scenario(harness, "N2a"))
    assert len(ledger) == 2, ledger
    assert ledger[0]["entries"] == [_entry("POST", "/api/notes/b/0", 10, None, None)]
    assert ledger[1]["entries"] == [] and ledger[1]["url"] == U1


def test_n2b_late_settle_from_doc0_does_not_clobber_doc1(harness: Dict[str, Any]) -> None:
    ledger = _ledger(_scenario(harness, "N2b"))
    assert len(ledger) == 2, ledger
    assert [(e["method"], e["status"]) for e in ledger[1]["entries"]] == [("GET", 200)]
    (post,) = ledger[0]["entries"]
    assert post["method"] == "POST" and post["status"] == 201 and post["settled"] is not None


def test_n3_only_the_ledger_key_is_touched(harness: Dict[str, Any]) -> None:
    res = _scenario(harness, "N3")
    final = res["final"]
    assert set(final) == {"r3_app", "other", "__r3_diag_fetch_ledger_x", KEY}, final
    assert final["r3_app"] == "v2"
    assert final["other"] == "{\"x\":1}"
    assert final["__r3_diag_fetch_ledger_x"] == "decoy"
    assert set(res["access"]) <= {"getItem", "setItem"}, sorted(set(res["access"]))
    assert res["calls"], "the ledger never touched storage at all"
    assert all(c["key"] == KEY for c in res["calls"]), res["calls"]


def test_n4_reinjection_is_idempotent(harness: Dict[str, Any]) -> None:
    res = _scenario(harness, "N4")
    assert res["netCalls"] == 3
    assert (res["len0"], res["len1"]) == (2, 1)
    ledger = _ledger(res)
    assert [len(s["entries"]) for s in ledger] == [2, 1]


def test_n5a_quota_exceeded_is_transparent(harness: Dict[str, Any]) -> None:
    res = _scenario(harness, "N5a")
    assert res["evalThrew"] is None
    assert res["firstSame"] is True
    assert res["rejectedSame"] is True and res["resolvedInstead"] is False
    log = res["log"]
    assert len(log) == 2
    assert log[0]["status"] == 201 and log[0]["settled"] is not None
    assert log[1]["error"] == res["errString"] and log[1]["settled"] is not None
    assert res["stored"] == {}


@pytest.mark.parametrize(
    "seed,prefix",
    [("{not json", []), ("null", []), ("{\"a\":1}", []), ("[1,2]", [1, 2])],
)
def test_n5b_corrupt_ledger_value_is_replaced_or_appended(
    harness: Dict[str, Any], seed: str, prefix: List[int]
) -> None:
    res = _scenario(harness, "N5b")[seed]
    assert res["evalThrew"] is None
    assert res["same"] is True
    assert res["logLen"] == 1
    ledger = _ledger(res)
    assert ledger[: len(prefix)] == prefix and len(ledger) == len(prefix) + 1, ledger
    own = ledger[-1]
    assert own["url"] == U0
    assert [(e["method"], e["status"]) for e in own["entries"]] == [("POST", 201)]


def test_n5c_storage_getter_throwing_is_transparent(harness: Dict[str, Any]) -> None:
    res = _scenario(harness, "N5c")
    assert res["evalThrew"] is None
    assert res["same"] is True
    assert [(e["method"], e["status"]) for e in res["log"]] == [("POST", 201)]


def test_n6_non_notes_requests_pass_through_untouched(harness: Dict[str, Any]) -> None:
    res = _scenario(harness, "N6")
    assert res["results"] == [{"reached": True, "same": True, "argsSame": True}] * 3
    assert res["logLen"] == 1
    assert res["snap"] is not None and res["after"] == res["snap"]


def test_n7_plugin_readback_script_round_trips(harness: Dict[str, Any]) -> None:
    assert harness["__readback__"] is not None, (
        "makereport never put an evaluate result into record['fetch_docs']"
    )
    res = _scenario(harness, "N7")
    assert "skipped" not in res, res
    assert res["afterN1"] == {"value": res["stored"]}
    assert res["absent"] == {"value": "__NO_LEDGER__"}
    assert res["corrupt"] == {"value": "{not json"}


def test_n8_non_top_frame_touches_no_storage(harness: Dict[str, Any]) -> None:
    res = _scenario(harness, "N8")
    assert res["evalThrew"] is None
    assert res["same"] is True
    assert res["getterHits"] == 0
    assert [(e["method"], e["status"]) for e in res["frameLog"]] == [("POST", 201)]
    assert res["before"] is not None and res["after"] == res["before"]


def test_n9_same_url_reload_keeps_both_segments(harness: Dict[str, Any]) -> None:
    ledger = _ledger(_scenario(harness, "N9"))
    assert len(ledger) == 2, ledger
    assert [e["method"] for e in ledger[0]["entries"]] == ["POST"]
    assert ledger[0]["entries"][0]["status"] == 201
    assert [e["method"] for e in ledger[1]["entries"]] == ["GET"]
    assert ledger[0]["doc"] != ledger[1]["doc"]


@pytest.mark.parametrize("name", ["NP1", "NP2"])
def test_np_properties_hold_over_random_programs(harness: Dict[str, Any], name: str) -> None:
    res = _scenario(harness, name)
    assert res["ok"] is True and res["numRuns"] == 200, (
        f"{name} failed (seed={res.get('seed')}):\n{res.get('error')}\n"
        f"counterexample: {res.get('counterexample')}"
    )


# --------------------------------------------------------------------------
# P1–P2 (Python side)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("fetch_fails", [False, True])
@pytest.mark.parametrize("docs_fails", [False, True])
def test_p1_fetch_and_fetch_docs_errors_are_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fetch_fails: bool, docs_fails: bool
) -> None:
    monkeypatch.setattr(diag, "_OUT", tmp_path)
    monkeypatch.setenv("E2E_DIAG_ALWAYS", "1")
    raising = frozenset(k for k, on in (("fetch", fetch_fails), ("fetch_docs", docs_fails)) if on)
    page = FakeLedgerPage(raising)
    _drive(SimpleNamespace(nodeid="tests/e2e/x.py::p1", funcargs={"page": page}), "call", "passed")
    (dump,) = tmp_path.glob("*.json")
    record = json.loads(dump.read_text(encoding="utf-8"))
    for key, marker in (("fetch", "log"), ("fetch_docs", "docs")):
        if key in raising:
            assert record.get(f"{key}_error") == f"Error: boom-{key}"
            assert key not in record
        else:
            assert key in page.index, f"{key} was never evaluated"
            assert record[key] == {marker: page.index[key]}
            assert f"{key}_error" not in record
    assert {"perf", "diag", "url", "test"} <= set(record)


_CHILD_INI = "[pytest]\naddopts = -p no:cacheprovider\n"

_CHILD_CONFTEST = textwrap.dedent('''
    import os

    import pytest
    from playwright.sync_api import Error as PlaywrightError

    KEY = "__r3_diag_fetch_ledger"


    class FakePage:
        url = "http://127.0.0.1:1/read/b/1"

        def __init__(self):
            self.n = 0
            self.ledger_reads = 0

        def add_init_script(self, _script):
            pass

        def evaluate(self, script, *_args):
            i = self.n
            self.n += 1
            if "__r3FetchLog" in script:
                return {"log": i}
            if KEY in script:
                self.ledger_reads += 1
                if os.environ.get("FAKE_LATE_LEDGER_RAISE") == "1" and self.ledger_reads > 1:
                    raise PlaywrightError("boom-late-ledger")
                return {"docs": i}
            return []


    @pytest.fixture
    def page():
        return FakePage()
''')

_CHILD_TEST = "def test_red(page):\n    assert False\n"


def _run_child(tmp: Path, late_raise: bool) -> Dict[str, Any]:
    tree = tmp / "tree"
    tree.mkdir(parents=True)
    (tree / "pytest.ini").write_text(_CHILD_INI, encoding="utf-8")
    (tree / "conftest.py").write_text(_CHILD_CONFTEST, encoding="utf-8")
    (tree / "test_red.py").write_text(_CHILD_TEST, encoding="utf-8")
    out = tmp / "out"
    env = dict(os.environ)
    env.pop("E2E_DIAG_ALWAYS", None)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO_ROOT / "scripts"), env.get("PYTHONPATH")]))
    env["E2E_DIAG_OUT"] = str(out)
    if late_raise:
        env["FAKE_LATE_LEDGER_RAISE"] = "1"
    else:
        env.pop("FAKE_LATE_LEDGER_RAISE", None)
    cmd = [sys.executable, "-m", "pytest", "-p", "e2e_diag_dump", "-p", "no:playwright", "-q", "test_red.py"]
    try:
        proc = subprocess.run(cmd, cwd=str(tree), env=env, capture_output=True, text=True, timeout=CHILD_TIMEOUT_S)
    except subprocess.TimeoutExpired:  # pragma: no cover - only when the child hangs
        pytest.fail(f"child pytest exceeded {CHILD_TIMEOUT_S}s: {cmd}")
    assert "1 failed" in proc.stdout and proc.returncode == 1, proc.stdout + proc.stderr
    files = sorted(out.glob("*.json")) if out.exists() else []
    assert len(files) == 1, (files, proc.stdout, proc.stderr)
    return json.loads(files[0].read_text(encoding="utf-8"))


def test_p2_teardown_reread_lands_as_late_fetch_docs(tmp_path: Path) -> None:
    rec = _run_child(tmp_path / "ok", late_raise=False)
    assert {"fetch", "fetch_docs", "late_fetch", "late_fetch_docs"} <= set(rec), sorted(rec)
    assert rec["late_fetch_docs"]["docs"] > rec["fetch_docs"]["docs"]

    rec2 = _run_child(tmp_path / "raise", late_raise=True)
    assert "boom" in rec2.get("late_error", ""), sorted(rec2)
    assert "fetch_docs" in rec2

"""Shared helpers for the 013 WI-9 contract-lint tests (A9.3 / A9.6* / A9.11* / A9.12 / A9.13).

Every lint under test takes a `--root <dir>` override, so counter-examples are seeded
into a `tmp_path` copy and never into the real tree. Python lints are loaded from their
path and driven in-process through `main(argv)`; the hardcode ratchet (Node) and the
`npm run lint:contracts` command are driven as bounded child processes.

Node missing is a failure, not a skip (see `frontend_host.require_node_toolchain`).
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import frontend_host as fh

REPO_ROOT = fh.REPO_ROOT
SCRIPTS = REPO_ROOT / "scripts"

INLINE_LINT = SCRIPTS / "lint_inline_html.py"
INLINE_ALLOWLIST_REL = "scripts/inline_html_allowlist.json"
MONOTONE_GUARD = SCRIPTS / "check_allowlist_monotone.py"
HARDCODE_LINT = SCRIPTS / "lint_hardcode.mjs"
HARDCODE_BASELINE_REL = "scripts/hardcode_baseline.json"
CONTRACTS = SCRIPTS / "lint_contracts.py"
NAMING_LINT = SCRIPTS / "lint_testid_naming.py"
TOKEN_REFS_LINT = SCRIPTS / "lint_token_refs.py"
SELECTOR_LINT = SCRIPTS / "lint_e2e_selectors.py"

TEMPLATES_REL = "src/reader3_app/web/templates"
TEMPLATE_NAMES = ("library.html", "reader.html", "settings.html")

#: The seven check names `lint:contracts` reports, in run order.
CONTRACT_CHECKS = (
    "selector",
    "naming",
    "token-ref",
    "inline-html",
    "hardcode",
    "allowlist-monotone",
    "depcruise",
)

NODE_TIMEOUT_S = 120
COMMAND_TIMEOUT_S = 240


# ---------------------------------------------------------------------------
# in-process Python lints
# ---------------------------------------------------------------------------
def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def call_main(module, argv: Sequence[str]) -> Tuple[int, str]:
    """`(exit code, stdout+stderr)` of `module.main(argv)`, normalising `sys.exit`."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = module.main(list(argv))
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    return int(code), out.getvalue() + err.getvalue()


def write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# tree copies
# ---------------------------------------------------------------------------
#: What the five lints + depcruise read. Copying exactly this keeps a tmp repo small
#: while letting every check run for real against it.
SCANNED_TREE = (
    TEMPLATES_REL,
    "src/reader3_app/web/static",
    "designs/reader-pro-next",
    "frontend/src",
    "frontend/aliases.ts",
    "tsconfig.json",
    ".dependency-cruiser.cjs",
    "scripts/token_ref_whitelist.txt",
    INLINE_ALLOWLIST_REL,
    HARDCODE_BASELINE_REL,
    "docs/plans/20260817-frontend-ui-refactor/spec-frontend-design.md",
    "docs/plans/20260817-frontend-ui-refactor/plan-frontend-ui-refactor.md",
)


def copy_scanned_tree(dest: Path) -> Path:
    ignore = shutil.ignore_patterns("__pycache__", ".DS_Store", "vendor", "dist", "node_modules")
    for rel in SCANNED_TREE:
        src = REPO_ROOT / rel
        target = dest / rel
        if src.is_dir():
            shutil.copytree(src, target, ignore=ignore)
        elif src.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
    # Selector lint scans tests/e2e/**/*.{py,ts,js}; the sources are enough.
    for p in sorted((REPO_ROOT / "tests" / "e2e").rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        target = dest / p.relative_to(REPO_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
    return dest


def copy_frontend_src(dest: Path) -> Path:
    """Just `frontend/src` plus a baseline restricted to its keys (hardcode-lint rows)."""
    shutil.copytree(REPO_ROOT / "frontend" / "src", dest / "frontend" / "src")
    baseline = read_baseline(REPO_ROOT)
    write_baseline(dest, {k: v for k, v in baseline.items() if k.startswith("frontend/src/")})
    return dest


def read_baseline(root: Path) -> Dict[str, List[str]]:
    p = root / HARDCODE_BASELINE_REL
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def write_baseline(root: Path, data: Dict[str, List[str]]) -> None:
    write(root, HARDCODE_BASELINE_REL, json.dumps(data, indent=2, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Node children
# ---------------------------------------------------------------------------
def run_hardcode(root: Path, *extra: str) -> subprocess.CompletedProcess:
    fh.require_node_toolchain()
    return fh.run(["node", str(HARDCODE_LINT), "--root", str(root), *extra], cwd=REPO_ROOT, timeout=NODE_TIMEOUT_S)


def hardcode_json(root: Path) -> Tuple[int, dict]:
    proc = run_hardcode(root, "--json")
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic path
        raise AssertionError(f"--json output is not JSON: {exc}\n{fh.describe(proc)}") from exc
    return proc.returncode, report


def run_contracts(root: Path, base_ref: Optional[str] = "base") -> subprocess.CompletedProcess:
    fh.require_node_toolchain()
    args = ["npm", "run", "--silent", "lint:contracts", "--", "--root", str(root)]
    if base_ref is not None:
        args += ["--base-ref", base_ref]
    return fh.run(args, cwd=REPO_ROOT, timeout=COMMAND_TIMEOUT_S)


def failed_checks(output: str) -> Optional[List[str]]:
    """Parse the summary line `lint:contracts: FAIL <a>, <b>` (None when it says OK)."""
    for line in output.splitlines()[::-1]:
        if line.startswith("lint:contracts: FAIL"):
            rest = line[len("lint:contracts: FAIL") :].strip(" :")
            return sorted(x.strip() for x in rest.split(",") if x.strip())
        if line.startswith("lint:contracts: OK"):
            return None
    raise AssertionError(f"no lint:contracts summary line in output:\n{output[-3000:]}")


# ---------------------------------------------------------------------------
# tmp git repos
# ---------------------------------------------------------------------------
GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", *GIT_ID, "-C", str(repo), *args], capture_output=True, text=True, timeout=60
    )
    if check:
        assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc


def init_repo(repo: Path, tag: str = "base") -> Path:
    repo.mkdir(parents=True, exist_ok=True)
    git(repo, "init", "-q", "-b", "work")
    commit_all(repo, "base")
    git(repo, "tag", tag)
    return repo


def commit_all(repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message)


def edit_json(root: Path, rel: str, mutate) -> None:
    p = root / rel
    data = json.loads(p.read_text(encoding="utf-8"))
    mutate(data)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def repo_status(root: Path = REPO_ROOT) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True, timeout=60
    ).stdout


def lines_matching(text: str, needles: Iterable[str]) -> List[str]:
    return [line for line in text.splitlines() if all(n in line for n in needles)]

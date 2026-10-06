"""The feature ledger as data: loading it, and sorting a row's Tests entries into runners.

The ledger is parsed by the repo's own `scripts/build_feature_ledger.py` (loaded from the
checkout this package lives in), so `lane` and `map check` read the ledger exactly as CI
does. Any parse error makes the ledger unusable: callers turn `LedgerError` into a
`ledger_invalid` envelope.

`classify` keeps every entry exactly as written (a note suffix such as
`path (asserts 0 requests)` included), so the four buckets always partition the input.
`build_argv` strips the note, normalizes the path and drops duplicates.
"""

import importlib.util
import os
from pathlib import Path

from verify_control import paths

LEDGER_REL = ("docs", "feature-ledger.md")
RUNNERS = ("pytest", "e2e", "vitest")
_PYTEST_PREFIXES = ("tests/unit/", "tests/contract/", "tests/integration/")
_E2E_PREFIX = "tests/e2e/"


class LedgerError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def _parser_module():
    script = paths.repo_root() / "scripts" / "build_feature_ledger.py"
    spec = importlib.util.spec_from_file_location("verify_control_build_feature_ledger", str(script))
    if spec is None or spec.loader is None:
        raise LedgerError(f"cannot load the ledger parser {script}")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except (OSError, SyntaxError) as exc:
        raise LedgerError(f"cannot load the ledger parser {script}: {exc}") from None
    return mod


def ledger_path(root):
    return Path(root).joinpath(*LEDGER_REL)


def load_features(root):
    """`{id: feature dict}` for the ledger under `root`; raises LedgerError."""
    path = ledger_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise LedgerError(f"cannot read the ledger {path}: {exc}") from None
    data, errors = _parser_module().parse_ledger(text)
    if errors:
        raise LedgerError(f"{path} does not parse: " + "; ".join(str(e) for e in errors))
    return {f["id"]: f for f in data.get("features", [])}


def is_absent(feature):
    words = str(feature.get("status", "")).split()
    return bool(words) and words[0] == "absent"


def strip_note(entry):
    """`path (note)` -> `path`, mirroring the ledger builder's `_entry_path`."""
    if entry.endswith(")") and " (" in entry:
        return entry.split(" (", 1)[0]
    return entry


def normalize(path):
    norm = os.path.normpath(path)
    if path.endswith("/") and not norm.endswith("/"):
        norm += "/"
    return norm


def runner_for(norm):
    if norm.startswith(_PYTEST_PREFIXES):
        return "pytest"
    if norm.startswith(_E2E_PREFIX):
        return "e2e"
    if norm.startswith("frontend/") and norm.endswith(".ts"):
        return "vitest"
    return None


def _outside(raw, norm):
    """Absolute, escaping the repo, or using `..` to climb out of the supported test trees.

    `tests/unit/../e2e/x.py` stays contained (it lands in `tests/e2e/`);
    `tests/unit/../../etc/passwd` does not, although it is lexically under the root.
    """
    if os.path.isabs(raw) or norm == ".." or norm.startswith("../"):
        return True
    return ".." in raw.split("/") and runner_for(norm) is None


def classify(entries, repo_root):
    """Partition `entries` into `{pytest, e2e, vitest, skipped}`; skipped items carry a reason."""
    out = {"pytest": [], "e2e": [], "vitest": [], "skipped": []}
    for entry in entries:
        raw = strip_note(entry)
        norm = normalize(raw)
        if _outside(raw, norm):
            out["skipped"].append({"entry": entry, "reason": "outside_repo"})
            continue
        runner = runner_for(norm)
        if runner is None:
            out["skipped"].append({"entry": entry, "reason": "unsupported"})
        elif not os.path.exists(os.path.join(str(repo_root), norm)):
            out["skipped"].append({"entry": entry, "reason": "missing"})
        else:
            out[runner].append(entry)
    return out


def build_argv(runner, entries):
    """The argv list for one runner over `entries` (notes stripped, normalized, deduplicated)."""
    seen, targets = set(), []
    for entry in entries:
        p = normalize(strip_note(entry))
        if p not in seen:
            seen.add(p)
            targets.append(p)
    if runner == "pytest":
        return ["uv", "run", "pytest", *targets]
    if runner == "e2e":
        return ["uv", "run", "python", "scripts/e2e_lock.py", "--", "uv", "run", "pytest", *targets,
                "--browser", "chromium"]
    if runner == "vitest":
        return ["npm", "test", "--", *targets]
    raise ValueError(f"unknown runner {runner!r}")

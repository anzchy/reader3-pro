#!/usr/bin/env python3
"""Feature ledger generator: `docs/feature-ledger.md` -> the `ledger-data`
JSON block of `docs/feature-ledger.html`.

**Why this script exists.** The HTML dashboard used to be hand-mirrored from
the md ("Rule 6"). Hand-mirroring drifts silently: a row is re-graded in the
md, the JSON keeps the old status, and the dashboard describes a product that
no longer exists. The md is the single source; this script derives the view
and (with `--check`) fails CI when the two disagree.

**Strict, never guessing.** Anything the parser cannot read exactly is an
error — a `|` inside a Summary cell, a malformed Synced line, a missing
section. Errors are aggregated into one list and returned, never raised one at
a time, so a single run names every defect.

**Stdlib only, Python 3.10.** The commit-gated unit lane runs this under the
repo's 3.10 interpreter: no `tomllib`, no `datetime.UTC`, no `except*`.

Stages (each returns / appends to a list of error strings):

1. `split_sections` + `parse_document` — document skeleton: H1, Synced line,
   top-level `## ` sections, the Summary table.            (WI-1)
2. `_parse_feature_sections` + `_tokenize_list` + `build_features` — feature
   sections -> feature dicts in Summary order.              (WI-2)
   Each section's area is its enclosing `###` heading.      (WI-10)
3. Row grammar / cross-row validation, incl. Summary Area
   == enclosing `###` heading.                              (WI-3, WI-10)
4. Repo-reference validation.                              (WI-4)
5. Audit log parse + Synced cross-check.                   (WI-5)
6. Render / splice / drift diff.                           (WI-6)
7. CLI.                                                    (WI-7)
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Value of the top-level `synced_from` key (repo-relative, POSIX).
SYNCED_FROM = "docs/feature-ledger.md"

#: Top-level JSON key order. Part of the page's data contract.
TOP_KEYS = ("synced_from", "synced_at", "commit", "statuses", "features", "audit")

#: The 8 base status tokens, in the md's "Status values" order.
STATUSES = (
    "accepted",
    "partial",
    "stub",
    "absent",
    "unknown",
    "deprecated",
    "superseded",
    "removed",
)

H1 = "# Feature Ledger"

#: Strict metadata line; must be the first non-blank line after the H1.
SYNCED_RE = re.compile(r"^\*\*Synced:\*\* (\d{4}-\d{2}-\d{2}) at commit `([0-9a-f]{7,40})`$")
#: Any line that *tries* to be the Synced line (used to count / locate it).
SYNCED_PREFIX = "**Synced:**"

SECTION_SUMMARY = "Summary"
SECTION_FEATURES = "Features"
SECTION_AUDIT = "Audit log"
REQUIRED_SECTIONS = (SECTION_SUMMARY, SECTION_FEATURES, SECTION_AUDIT)

SUMMARY_COLUMNS = ("ID", "Feature", "Area", "Status", "Evidence")

#: Feature bullet labels, in the md's Row grammar order.
LABEL_ORDER = ("What", "Routes", "Code", "Tests", "Confirm", "Tracked", "Evidence", "Limits")
#: Feature dict key order. Part of the page's data contract.
FEATURE_KEYS = (
    "id",
    "name",
    "area",
    "status",
    "what",
    "routes",
    "code",
    "tests",
    "adr",
    "confirm",
    "tracked",
    "evidence",
    "limits",
)
REQ, OPT, FORBID = "required", "optional", "forbidden"
_ROW_ACCEPTED = {
    "What": REQ,
    "Routes": OPT,
    "Code": REQ,
    "Tests": REQ,
    "Confirm": REQ,
    "Tracked": FORBID,
    "Evidence": REQ,
    "Limits": OPT,
}
_ROW_STUB = dict(_ROW_ACCEPTED, Tests=OPT)
_ROW_ABSENT = dict(
    _ROW_ACCEPTED, Code=FORBID, Tests=FORBID, Confirm=FORBID, Tracked=REQ, Evidence=FORBID
)
_ROW_RETIRED = dict(_ROW_ACCEPTED, Tests=OPT, Confirm=OPT)
#: `removed`: the paths no longer exist (history is in git), so Code/Tests are
#: forbidden and Evidence (the removal PR/SHA) is required.
_ROW_REMOVED = dict(_ROW_RETIRED, Code=FORBID, Tests=FORBID)
#: `ROW_GRAMMAR[base status][label]` in {required, optional, forbidden}: the
#: md's Row grammar table, plus the `removed` row (orchestrator resolution,
#: 2026-09-27). `Tracked` is forbidden everywhere but `absent`.
ROW_GRAMMAR = {
    "accepted": _ROW_ACCEPTED,
    "partial": _ROW_ACCEPTED,
    "stub": _ROW_STUB,
    "unknown": _ROW_STUB,
    "absent": _ROW_ABSENT,
    "deprecated": _ROW_RETIRED,
    "superseded": _ROW_RETIRED,
    "removed": _ROW_REMOVED,
}
ID_RE = re.compile(r"^F-\d{3}$")
SUPERSEDED_RE = re.compile(r"^superseded → (F-\d{3})$")

#: Labels whose value is a tokenized list; every other label is a verbatim string.
LIST_LABELS = ("Routes", "Code", "Tests")

FEATURE_HEADING = "#### "
AREA_HEADING = "### "
HEADING_SEP = " — "
#: A `###` heading that is really a feature written one level too high.
MISLEVELLED_FEATURE_RE = re.compile(r"^F-\d")
BULLET_RE = re.compile(r"^- \*\*([^*]+):\*\*(.*)$")
ADR_LIST_RE = re.compile(r"^ADR-\d{4}(?:, ADR-\d{4})*$")
SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")

SNAPSHOT_REL = "tests/contract/routes.snapshot"
PYPROJECT_REL = "pyproject.toml"
SCRIPTS_HEADER = "[project.scripts]"
SCRIPT_LINE_RE = re.compile(r'^([A-Za-z0-9_.-]+)\s*=\s*"[^"]*"\s*$')
#: Routes entries with this prefix name a `[project.scripts]` key, not an HTTP route.
CLI_PREFIX = "cli: "

AUDIT_HEADING = "### "
AUDIT_HEADING_RE = re.compile(r"^### (\d{4}-\d{2}-\d{2}) — (.+) \(`([0-9a-f]{7,40})`\)$")
#: Audit entry bullets: all required, exactly these, in this order.
AUDIT_LABELS = ("Scope", "Found", "Not audited")
#: Audit entry JSON key order. Part of the page's data contract.
AUDIT_KEYS = ("date", "title", "commit", "scope", "found", "not_audited")


class SummaryRow:
    """One `## Summary` table row, cells verbatim."""

    def __init__(
        self, id: str, name: str, area: str, status: str, evidence: str, line_no: int
    ) -> None:
        self.id = id
        self.name = name
        self.area = area
        self.status = status
        self.evidence = evidence
        self.line_no = line_no  # 1-based line in the md


class FeatureSection:
    """One `#### F-NNN Name — status` section under `## Features`, raw.

    `labels` keeps the bullet labels in the order they were written (duplicates
    and unknown labels are dropped here and reported), so row-grammar checks
    can judge ordering without re-reading the md.
    """

    def __init__(self, id: str, name: str, status: str, line_no: int) -> None:
        self.id = id
        self.name = name
        self.status = status
        self.line_no = line_no  # 1-based line of the heading
        #: Text and 1-based line of the nearest preceding `###` area heading
        #: under `## Features`; `None` when the section has none (an error).
        self.area: str | None = None
        self.area_line = 0
        self.labels: list[str] = []
        self.values: dict[str, str] = {}  # label -> raw bullet value
        self.feature: dict = {}  # tokenized feature dict (area filled from Summary)


class Document:
    """The md split into the pieces later stages consume.

    Plain classes, not `@dataclass`: tests load this script with
    `spec_from_file_location` without registering it in `sys.modules`, and
    `dataclasses` needs `sys.modules[cls.__module__]` (same reason
    `check_router_size.Exemption` is a plain class).
    """

    def __init__(self) -> None:
        self.synced_at = ""
        self.commit = ""
        #: `## ` heading text -> body lines (heading excluded), up to the next `## `.
        self.sections: dict[str, list[str]] = {}
        #: `## ` heading text -> 1-based line number of the first body line.
        self.section_starts: dict[str, int] = {}
        self.summary: list[SummaryRow] = []
        #: Every well-formed `####` section under `## Features`, in file order
        #: (duplicate IDs kept; reported by row-grammar validation).
        self.feature_sections: list[FeatureSection] = []
        #: Audit log entries with a well-formed heading, in file order.
        self.audit: list[dict] = []


def _is_h2(line: str) -> bool:
    return line.startswith("## ")


def split_sections(md_text: str) -> dict[str, list[str]]:
    """Top-level `## ` sections: heading text -> body lines.

    A section runs to the next `## ` heading or end of file, so `### ` and
    `#### ` headings under `## Audit log` stay in the audit section and can
    never be read as feature groups. A duplicated heading keeps its first
    occurrence (duplicates are reported by `parse_document`).
    """
    return _split(md_text.split("\n"))[0]


def _split(lines: list[str]) -> tuple[dict[str, list[str]], dict[str, int], list[str]]:
    sections: dict[str, list[str]] = {}
    starts: dict[str, int] = {}
    duplicates: list[str] = []
    current: list[str] | None = None
    for i, line in enumerate(lines):
        if _is_h2(line):
            name = line[3:].strip()
            if name in sections:
                duplicates.append(name)
                current = []  # read, but discarded
            else:
                current = sections[name] = []
                starts[name] = i + 2
            continue
        if current is not None:
            current.append(line)
    return sections, starts, duplicates


def _parse_synced(lines: list[str]) -> tuple[str, str, list[str]]:
    """Return (synced_at, commit, errors). At most one error, always naming Synced."""
    hits = [i for i, line in enumerate(lines) if line.startswith(SYNCED_PREFIX)]
    fmt = "**Synced:** YYYY-MM-DD at commit `<7-40 lowercase hex>`"
    if not hits:
        return "", "", [f"Synced line missing: expected `{fmt}` directly under `{H1}`."]
    if len(hits) > 1:
        where = ", ".join(str(i + 1) for i in hits)
        return "", "", [f"Synced line appears {len(hits)} times (lines {where}); exactly one allowed."]
    idx = hits[0]
    line = lines[idx]
    h1_idx = next((i for i, x in enumerate(lines) if x.rstrip() == H1), None)
    if h1_idx is None:
        return "", "", [f"Synced line (line {idx + 1}) must sit directly under `{H1}`, which is missing."]
    first = next((i for i in range(h1_idx + 1, len(lines)) if lines[i].strip()), None)
    if first != idx:
        return "", "", [
            f"Synced line (line {idx + 1}) must be the first non-blank line under `{H1}`."
        ]
    m = SYNCED_RE.match(line)
    if m is None:
        return "", "", [f"Synced line (line {idx + 1}) malformed: {line!r}; expected `{fmt}`."]
    synced_at, commit = m.group(1), m.group(2)
    try:
        date.fromisoformat(synced_at)
    except ValueError:
        return "", "", [f"Synced line (line {idx + 1}) has an invalid date {synced_at!r}."]
    return synced_at, commit, []


def _split_row(line: str) -> list[str] | None:
    """Cells of a `| a | b |` line, or None if it is not a table row."""
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|") and len(s) >= 2):
        return None
    return [c.strip() for c in s[1:-1].split("|")]


def _parse_summary(body: list[str], first_line_no: int) -> tuple[list[SummaryRow], list[str]]:
    errors: list[str] = []
    rows: list[SummaryRow] = []
    table = [(first_line_no + i, line) for i, line in enumerate(body) if line.strip()]
    if not table:
        return [], ["Summary section has no table."]

    header_no, header = table[0]
    if _split_row(header) != list(SUMMARY_COLUMNS):
        expected = "| " + " | ".join(SUMMARY_COLUMNS) + " |"
        errors.append(f"Summary header (line {header_no}) must be `{expected}`, got {header!r}.")
        return [], errors
    if len(table) < 2:
        return [], [f"Summary table (line {header_no}) has no separator row and zero rows."]
    sep_no, sep = table[1]
    sep_cells = _split_row(sep)
    if (
        sep_cells is None
        or len(sep_cells) != len(SUMMARY_COLUMNS)
        or not all(SEPARATOR_CELL_RE.match(c) for c in sep_cells)
    ):
        errors.append(f"Summary separator (line {sep_no}) malformed: {sep!r}.")

    for line_no, line in table[2:]:
        cells = _split_row(line)
        if cells is None:
            errors.append(f"Summary line {line_no} is not a table row: {line!r}.")
            continue
        row_id = cells[0] if cells and cells[0] else f"line {line_no}"
        if "\\|" in line:
            errors.append(
                f"Summary row {row_id} (line {line_no}): escaped `\\|` in a cell is not "
                "supported; a cell may not contain `|`."
            )
            continue
        if len(cells) != len(SUMMARY_COLUMNS):
            errors.append(
                f"Summary row {row_id} (line {line_no}) has {len(cells)} cells, expected "
                f"{len(SUMMARY_COLUMNS)} (a `|` inside a cell is an error, not a guess)."
            )
            continue
        rows.append(SummaryRow(*cells, line_no=line_no))

    if not rows and not errors:
        errors.append(f"Summary table (line {header_no}) has zero rows.")
    return rows, errors


def _match_paren(s: str, open_idx: int) -> int:
    """Index of the `)` matching `s[open_idx] == "("`, or -1. Backticked spans are opaque."""
    depth = 0
    in_code = False
    for i in range(open_idx, len(s)):
        ch = s[i]
        if ch == "`":
            in_code = not in_code
        elif not in_code and ch == "(":
            depth += 1
        elif not in_code and ch == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _tokenize_list(value: str, notes: bool, adr: bool) -> tuple[list[str], list[str], str]:
    """`` `a`, `b` (note) · ADR-NNNN `` -> (entries, adrs, error reason or "").

    The whole value must be consumed; anything left over is an error, never
    dropped. A note runs to its matching `)` and stays verbatim in its entry.
    """
    entries: list[str] = []
    i, n = 0, len(value)
    while True:
        if i >= n or value[i] != "`":
            return entries, [], f"expected a backticked entry at column {i + 1}"
        close = value.find("`", i + 1)
        if close == -1:
            return entries, [], "unbalanced backtick"
        entry = value[i + 1 : close]
        if not entry.strip():
            return entries, [], f"empty backticked entry at column {i + 1}"
        i = close + 1
        if notes and value.startswith(" (", i):
            end = _match_paren(value, i + 1)
            if end == -1:
                return entries, [], "unclosed parenthetical note"
            note = value[i + 2 : end]
            if not note.strip():
                return entries, [], "empty parenthetical note"
            entry = f"{entry} ({note})"
            i = end + 1
        entries.append(entry)
        if i == n:
            return entries, [], ""
        if value.startswith(", ", i):
            i += 2
            continue
        if adr and value.startswith(" · ", i):
            tail = value[i + 3 :]
            if not ADR_LIST_RE.match(tail):
                return entries, [], f"ADR list {tail!r} must be `ADR-NNNN(, ADR-NNNN)*`"
            return entries, tail.split(", "), ""
        return entries, [], f"unexpected text {value[i:]!r} at column {i + 1}"


def _parse_feature_heading(line: str, line_no: int) -> tuple[FeatureSection | None, str]:
    text = line[len(FEATURE_HEADING) :].strip()
    head, sep, status = text.rpartition(HEADING_SEP)
    fid, _, name = head.partition(" ")
    if not sep or not fid or not name.strip() or not status.strip():
        return None, (
            f"Feature heading {text!r} (line {line_no}) must be `F-NNN Name — status` "
            "(em dash, split on the last ` — `)."
        )
    return FeatureSection(fid, name.strip(), status.strip(), line_no), ""


def _parse_feature_sections(body: list[str], first_line_no: int) -> tuple[list[FeatureSection], list[str]]:
    """Split `## Features` into `####` sections and read their bullets.

    Every `####` section belongs to the nearest preceding `###` area heading;
    a section with none is an error. Before the first `####`, and between a
    `###` area heading and the next `####`, prose is ignored (ruling 7) — but
    a `- ` bullet there is an error, and so is a `### F-<digit>` heading:
    either would otherwise be a feature that silently vanished (review M2).
    Inside a `####` section every non-blank line up to the next heading must
    be a `- **Label:** value` bullet.
    """
    errors: list[str] = []
    sections: list[FeatureSection] = []
    current: FeatureSection | None = None
    in_section = False  # True inside a `####` block, even a malformed one
    area: str | None = None
    area_line = 0
    for offset, line in enumerate(body):
        line_no = first_line_no + offset
        if line.startswith(FEATURE_HEADING):
            in_section = True
            current, err = _parse_feature_heading(line, line_no)
            if current is None:
                errors.append(err)
                continue
            sections.append(current)
            current.area, current.area_line = area, area_line
            if area is None:
                errors.append(
                    f"{current.id} (line {line_no}): `####` section has no enclosing `###` area "
                    f"heading under `## {SECTION_FEATURES}`."
                )
            continue
        if line.startswith(AREA_HEADING):
            in_section, current = False, None
            text = line[len(AREA_HEADING) :].strip()
            if MISLEVELLED_FEATURE_RE.match(text):
                errors.append(
                    f"Features heading {text!r} (line {line_no}): feature heading must be `####`, "
                    "not `###` (a `###` heading is an area)."
                )
                continue
            area, area_line = text, line_no
            continue
        if not in_section:
            if line.startswith("- "):
                errors.append(
                    f"Features line {line_no}: bullet {line!r} is outside any `####` feature "
                    "section; it would be dropped."
                )
            continue
        if not line.strip() or current is None:
            continue
        m = BULLET_RE.match(line)
        if m is None:
            errors.append(
                f"{current.id} (line {line_no}): expected a `- **Label:** value` bullet, got "
                f"{line!r} (continuation and prose lines are not allowed inside a feature)."
            )
            continue
        label, value = m.group(1), m.group(2).strip()
        if label not in LABEL_ORDER:
            errors.append(
                f"{current.id} (line {line_no}): unknown label {label!r}; "
                f"expected one of {', '.join(LABEL_ORDER)}."
            )
            continue
        if label in current.values:
            errors.append(f"{current.id} (line {line_no}): duplicate {label} bullet.")
            continue
        if not value:
            errors.append(f"{current.id} (line {line_no}): {label} bullet has an empty value.")
            continue
        current.labels.append(label)
        current.values[label] = value
    return sections, errors


def _feature_dict(sec: FeatureSection, errors: list[str]) -> dict:
    """Tokenize one section into the feature dict (`area` left empty)."""
    lists: dict[str, list[str]] = {"Routes": [], "Code": [], "Tests": []}
    adrs: list[str] = []
    for label in LIST_LABELS:
        if label not in sec.values:
            continue
        value = sec.values[label]
        entries, found_adrs, reason = _tokenize_list(
            value, notes=label != "Routes", adr=label == "Code"
        )
        if reason:
            errors.append(f"{sec.id} {label}: {reason} in {value!r}.")
            continue
        lists[label] = entries
        if label == "Code":
            adrs = found_adrs
    text = {label: sec.values.get(label, "") for label in LABEL_ORDER if label not in LIST_LABELS}
    feature = {
        "id": sec.id,
        "name": sec.name,
        "area": "",
        "status": sec.status,
        "what": text["What"],
        "routes": lists["Routes"],
        "code": lists["Code"],
        "tests": lists["Tests"],
        "adr": adrs,
        "confirm": text["Confirm"],
        "tracked": text["Tracked"],
        "evidence": text["Evidence"],
        "limits": text["Limits"],
    }
    assert tuple(feature) == FEATURE_KEYS
    return feature


def _finish_audit_entry(entry: dict, labels: list[str], name: str, errors: list[str]) -> None:
    """Every audit label present, and in `AUDIT_LABELS` order."""
    for label in AUDIT_LABELS:
        if label not in labels:
            errors.append(f"{name}: {label} bullet is missing.")
    for prev, cur in zip(labels, labels[1:]):
        if AUDIT_LABELS.index(prev) > AUDIT_LABELS.index(cur):
            errors.append(f"{name}: {cur} must come before {prev} (order: {', '.join(AUDIT_LABELS)}).")


def _parse_audit(body: list[str], first_line_no: int) -> tuple[list[dict], list[str]]:
    """`## Audit log` -> entries in file order.

    Prose before the first `### ` heading is ignored. Inside an entry every
    non-blank line up to the next `### ` must be a Scope / Found / Not audited
    bullet; each error names the entry by its date and title. An entry with a
    malformed heading is reported once and its body is skipped. Zero headings
    is an error: an empty log would read as "never audited" silently.
    """
    errors: list[str] = []
    entries: list[dict] = []
    headings = 0
    entry: dict | None = None
    labels: list[str] = []
    name = ""
    for offset, line in enumerate(body):
        line_no = first_line_no + offset
        if line.startswith(AUDIT_HEADING):
            if entry is not None:
                _finish_audit_entry(entry, labels, name, errors)
            headings += 1
            entry, labels = None, []
            text = line[len(AUDIT_HEADING) :]
            m = AUDIT_HEADING_RE.match(line)
            if m is None:
                errors.append(
                    f"Audit heading {text!r} (line {line_no}) must be "
                    "`### YYYY-MM-DD — Title (`<7-40 lowercase hex>`)` (em dash, backticked sha)."
                )
                continue
            try:
                date.fromisoformat(m.group(1))
            except ValueError:
                errors.append(f"Audit heading {text!r} (line {line_no}) has an invalid date {m.group(1)!r}.")
                continue
            name = f"Audit entry `{m.group(1)} — {m.group(2)}`"
            entry = dict.fromkeys(AUDIT_KEYS, "")
            entry.update(date=m.group(1), title=m.group(2), commit=m.group(3))
            entries.append(entry)
            continue
        if entry is None or not line.strip():
            continue
        bullet = BULLET_RE.match(line)
        if bullet is None:
            errors.append(
                f"{name} (line {line_no}): expected a `- **Label:** value` bullet, got {line!r} "
                "(prose and continuation lines are not allowed inside an audit entry)."
            )
            continue
        label, value = bullet.group(1), bullet.group(2).strip()
        if label not in AUDIT_LABELS:
            errors.append(
                f"{name} (line {line_no}): unknown label {label!r}; expected {', '.join(AUDIT_LABELS)}."
            )
            continue
        if label in labels:
            errors.append(f"{name} (line {line_no}): duplicate {label} bullet.")
            continue
        if not value:
            errors.append(f"{name} (line {line_no}): {label} bullet has an empty value.")
            continue
        labels.append(label)
        entry[AUDIT_KEYS[3 + AUDIT_LABELS.index(label)]] = value
    if entry is not None:
        _finish_audit_entry(entry, labels, name, errors)
    if headings == 0:
        errors.append(f"Section `## {SECTION_AUDIT}` has zero entries; at least one `### ` entry is required.")
    return entries, errors


def parse_document(md_text: str) -> tuple[Document, list[str]]:
    """WI-1 skeleton: Synced line, section extents, Summary table."""
    errors: list[str] = []
    lines = md_text.split("\n")
    doc = Document()

    doc.synced_at, doc.commit, synced_errors = _parse_synced(lines)
    errors += synced_errors

    doc.sections, doc.section_starts, duplicates = _split(lines)
    for name in duplicates:
        errors.append(f"Section `## {name}` appears more than once.")
    for name in REQUIRED_SECTIONS:
        if name not in doc.sections:
            errors.append(f"Section `## {name}` is missing.")

    if SECTION_SUMMARY in doc.sections:
        doc.summary, summary_errors = _parse_summary(
            doc.sections[SECTION_SUMMARY], doc.section_starts[SECTION_SUMMARY]
        )
        errors += summary_errors

    if SECTION_FEATURES in doc.sections:
        doc.feature_sections, feature_errors = _parse_feature_sections(
            doc.sections[SECTION_FEATURES], doc.section_starts[SECTION_FEATURES]
        )
        errors += feature_errors
        for sec in doc.feature_sections:
            sec.feature = _feature_dict(sec, errors)

    if SECTION_AUDIT in doc.sections:
        doc.audit, audit_errors = _parse_audit(
            doc.sections[SECTION_AUDIT], doc.section_starts[SECTION_AUDIT]
        )
        errors += audit_errors

    return doc, errors


def build_features(doc: Document) -> list[dict]:
    """Feature dicts in Summary order, `area` from the Summary row (which
    `validate_rows` holds equal to the section's `###` heading).

    A Summary row without a section (or the reverse) is skipped here and
    reported by row-grammar validation; section order in the md is free.
    """
    by_id: dict[str, FeatureSection] = {}
    for sec in doc.feature_sections:
        by_id.setdefault(sec.id, sec)
    features = []
    for row in doc.summary:
        sec = by_id.get(row.id)
        if sec is None:
            continue
        features.append(dict(sec.feature, area=row.area))
    return features


def _data(doc: Document) -> dict:
    return {
        "synced_from": SYNCED_FROM,
        "synced_at": doc.synced_at,
        "commit": doc.commit,
        "statuses": list(STATUSES),
        "features": build_features(doc),
        "audit": [dict(a) for a in doc.audit],
    }


def parse_ledger(md_text: str) -> tuple[dict, list[str]]:
    """md text -> (data, parse errors). `data` always has `TOP_KEYS` in order.

    Parse stage only; `validate` adds the cross-row checks.
    """
    doc, errors = parse_document(md_text)
    return _data(doc), errors


def _check_ids(doc: Document, errors: list[str]) -> None:
    """ID format, uniqueness, and Summary = F-001..F-N ascending."""
    seen_bad: set[str] = set()
    for fid in [r.id for r in doc.summary] + [s.id for s in doc.feature_sections]:
        if not ID_RE.match(fid) and fid not in seen_bad:
            seen_bad.add(fid)
            errors.append(f"ID {fid!r} must match `F-NNN` (three digits).")

    for kind, ids in (
        ("Summary row", [r.id for r in doc.summary]),
        ("`####` section", [s.id for s in doc.feature_sections]),
    ):
        counted: set[str] = set()
        for fid in ids:
            if ids.count(fid) > 1 and fid not in counted:
                counted.add(fid)
                errors.append(f"{fid}: duplicate ID ({ids.count(fid)} {kind}s).")

    for i, row in enumerate(doc.summary):
        expected = f"F-{i + 1:03d}"
        if row.id != expected:
            errors.append(
                f"Summary row {i + 1} (line {row.line_no}) has ID {row.id!r}, expected "
                f"{expected!r}: Summary IDs must run F-001..F-N ascending with no gap or duplicate."
            )
            break  # one deviation breaks every later position; report the first only


def _check_status(sec: FeatureSection, ids: set[str], errors: list[str]) -> str | None:
    """Vocabulary check; returns the base status if it is one of the 8."""
    status = sec.status
    base = status.split()[0] if status.split() else ""
    if base not in STATUSES:
        errors.append(
            f"{sec.id}: unknown status {status!r}; base status must be one of {', '.join(STATUSES)}."
        )
        return None
    if base == "superseded":
        m = SUPERSEDED_RE.match(status)
        if m is None:
            errors.append(f"{sec.id}: status {status!r} must be `superseded → F-NNN`.")
        elif m.group(1) == sec.id:
            errors.append(f"{sec.id}: status {status!r} names the row itself as its successor.")
        elif m.group(1) not in ids:
            errors.append(f"{sec.id}: status {status!r} names {m.group(1)}, which is not in the Summary.")
    elif status != base:
        errors.append(f"{sec.id}: status {status!r} must be the single token {base!r}.")
    return base


def _check_labels(sec: FeatureSection, base: str | None, errors: list[str]) -> None:
    """Per-status required/forbidden labels, and `LABEL_ORDER`."""
    if base is not None:
        rules = ROW_GRAMMAR[base]
        for label in LABEL_ORDER:
            present = label in sec.labels
            if rules[label] == REQ and not present:
                errors.append(f"{sec.id}: {label} is required for status `{base}` but missing.")
            elif rules[label] == FORBID and present:
                errors.append(f"{sec.id}: {label} is forbidden for status `{base}`.")
    for prev, cur in zip(sec.labels, sec.labels[1:]):
        if LABEL_ORDER.index(prev) > LABEL_ORDER.index(cur):
            errors.append(
                f"{sec.id}: {cur} must come before {prev} (order: {', '.join(LABEL_ORDER)})."
            )


def validate_rows(doc: Document) -> list[str]:
    """Row grammar + cross-row checks (WI-3). Structural only, no filesystem.

    Every check appends; nothing returns early, so one run names every defect.
    Section order in the md is free — only the Summary order is checked.
    """
    errors: list[str] = []
    _check_ids(doc, errors)

    summary_ids = {r.id for r in doc.summary}
    sections: dict[str, FeatureSection] = {}
    for sec in doc.feature_sections:
        sections.setdefault(sec.id, sec)
        base = _check_status(sec, summary_ids, errors)
        _check_labels(sec, base, errors)
        if sec.id not in summary_ids:
            errors.append(f"{sec.id}: `####` section (line {sec.line_no}) has no Summary row.")

    for row in doc.summary:
        if not row.area:
            errors.append(f"{row.id}: Summary Area cell (line {row.line_no}) is empty.")
        sec = sections.get(row.id)
        if sec is None:
            errors.append(f"{row.id}: Summary row (line {row.line_no}) has no `####` section.")
            continue
        if row.area and sec.area is not None and row.area != sec.area:
            errors.append(
                f"{row.id}: Summary Area {row.area!r} (line {row.line_no}) differs from the "
                f"`###` heading {sec.area!r} (line {sec.area_line}) its section sits under."
            )
        if row.name != sec.name:
            errors.append(
                f"{row.id}: Summary name {row.name!r} differs from section name {sec.name!r}."
            )
        if row.status != sec.status:
            errors.append(
                f"{row.id}: Summary status {row.status!r} differs from section status {sec.status!r}."
            )
    return errors


def _entry_path(entry: str) -> str:
    """`path (note)` -> `path`. The note is kept in the JSON, never checked."""
    if entry.endswith(")") and " (" in entry:
        return entry.split(" (", 1)[0]
    return entry


def _check_paths(features: list[dict], root: Path, errors: list[str]) -> None:
    """Every Code/Tests entry exists under `root`; nothing may point outside it.

    Containment is lexical (`normpath`), so `a/../b.py` inside the root is
    fine and `../x.py` is rejected even when `x.py` exists: the ledger records
    repo paths, and a path outside the repo is not one whatever is on disk.
    """
    # Absolute first: with a relative root (`--root .`) `commonpath` compares
    # "." against "src/x" and returns "", so every path looked outside.
    base = os.path.normpath(str(Path(root).resolve()))
    for f in features:
        for label, key in (("Code", "code"), ("Tests", "tests")):
            for entry in f[key]:
                rel = _entry_path(entry)
                if os.path.isabs(rel):
                    errors.append(f"{f['id']} {label}: `{rel}` is absolute; paths are repo-relative.")
                    continue
                target = os.path.normpath(os.path.join(base, rel))
                if os.path.commonpath([base, target]) != base:
                    errors.append(f"{f['id']} {label}: `{rel}` resolves outside the repo root.")
                elif not os.path.exists(target):
                    errors.append(f"{f['id']} {label}: `{rel}` does not exist in the repo.")


def read_snapshot_routes(root: Path) -> tuple[list[str], list[str]]:
    """Route lines of `tests/contract/routes.snapshot` -> (routes, errors).

    Missing file or zero route lines is an error: an empty universe would make
    every claim check vacuous, which is a skip dressed up as a pass.
    """
    path = root / SNAPSHOT_REL
    if not path.is_file():
        return [], [f"{SNAPSHOT_REL} is missing; the route universe cannot be read."]
    routes = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        line = line.rstrip()
        if line and not line.startswith("#"):
            routes.append(line)
    if not routes:
        return [], [f"{SNAPSHOT_REL} has zero route lines."]
    return routes, []


def read_project_scripts(root: Path) -> tuple[list[str], list[str]]:
    """`[project.scripts]` keys of `pyproject.toml` -> (names, errors).

    A strict line scanner, not a TOML parser (no `tomllib` on 3.10): from the
    `[project.scripts]` header to the next `[` header, every non-blank,
    non-comment line must be `name = "value"` exactly, or it is an error.
    """
    path = root / PYPROJECT_REL
    if not path.is_file():
        return [], [f"{PYPROJECT_REL} is missing; `[project.scripts]` cannot be read."]
    lines = path.read_text(encoding="utf-8").split("\n")
    start = next((i for i, x in enumerate(lines) if x.strip() == SCRIPTS_HEADER), None)
    if start is None:
        return [], [f"{PYPROJECT_REL} has no `{SCRIPTS_HEADER}` section."]
    names: list[str] = []
    errors: list[str] = []
    for i in range(start + 1, len(lines)):
        line = lines[i].strip()
        if line.startswith("["):
            break
        if not line or line.startswith("#"):
            continue
        m = SCRIPT_LINE_RE.match(line)
        if m is None:
            errors.append(
                f"{PYPROJECT_REL} line {i + 1}: cannot read {lines[i]!r} under "
                f'`{SCRIPTS_HEADER}`; expected `name = "module:func"`.'
            )
            continue
        names.append(m.group(1))
    if not names and not errors:
        errors.append(f"{PYPROJECT_REL} `{SCRIPTS_HEADER}` has zero entries.")
    return names, errors


def validate_refs(data: dict, repo_root: Path) -> list[str]:
    """Repo-reference validation (WI-4): paths, route snapshot, CLI scripts, claims.

    Universe = snapshot route lines + `cli: <name>` per `[project.scripts]`
    key. A claim outside the universe names its row; a universe member no row
    claims is named too; several rows may claim one route. When a source
    cannot be read its own error stands for it, and claims of that kind are
    not re-reported one by one.
    """
    root = Path(repo_root)
    features = data["features"]
    errors: list[str] = []
    _check_paths(features, root, errors)

    routes, route_errors = read_snapshot_routes(root)
    scripts, script_errors = read_project_scripts(root)
    errors += route_errors + script_errors
    route_set = set(routes)
    cli_set = {CLI_PREFIX + name for name in scripts}

    claimed: set[str] = set()
    for f in features:
        for route in f["routes"]:
            claimed.add(route)
            if route.startswith(CLI_PREFIX):
                if not script_errors and route not in cli_set:
                    errors.append(
                        f"{f['id']} Routes: `{route}` is not a script in "
                        f"{PYPROJECT_REL} `{SCRIPTS_HEADER}`."
                    )
            elif not route_errors and route not in route_set:
                errors.append(f"{f['id']} Routes: `{route}` is not a route in {SNAPSHOT_REL}.")

    for route in routes:
        if route not in claimed:
            errors.append(f"`{route}` ({SNAPSHOT_REL}) is claimed by no feature's Routes.")
    for name in scripts:
        if CLI_PREFIX + name not in claimed:
            errors.append(
                f"`{CLI_PREFIX}{name}` ({PYPROJECT_REL} `{SCRIPTS_HEADER}`) is claimed by "
                "no feature's Routes."
            )
    return errors


def validate_audit(doc: Document) -> list[str]:
    """Audit date order + the Synced cross-check (WI-5).

    Dates must not increase down the file (same-day entries are fine). The
    Synced date must be `>=` the newest audit date: an audit entry added
    without bumping Synced is the one staleness this can catch without git.
    ISO dates compare correctly as strings; unreadable dates never get here.
    """
    errors: list[str] = []
    dates = [a["date"] for a in doc.audit]
    for above, below in zip(dates, dates[1:]):
        if below > above:
            errors.append(
                f"Audit log order: entry dated {below} sits below one dated {above}; "
                "entries must be newest first."
            )
    if doc.synced_at and dates and doc.synced_at < max(dates):
        errors.append(
            f"Synced date {doc.synced_at} is earlier than the newest Audit log entry "
            f"({max(dates)}); bump the Synced line."
        )
    return errors


def validate(md_text: str, repo_root: Path | None = None) -> tuple[dict, list[str]]:
    """The validation pipeline: parse, then every validator; all errors aggregated.

    With `repo_root`, repo references (paths, routes, CLI scripts) are
    checked too; without it the pipeline stays pure. Later stages append here.
    """
    doc, errors = parse_document(md_text)
    errors += validate_rows(doc)
    errors += validate_audit(doc)
    data = _data(doc)
    if repo_root is not None:
        errors += validate_refs(data, repo_root)
    return data, errors


# ---------------------------------------------------------------------------
# WI-6: render / splice / drift diff (pure)
# ---------------------------------------------------------------------------


#: The one opening tag `splice` looks for. Matched in full: the bare string
#: `ledger-data` also appears in the page's header comment and footer.
BLOCK_OPEN = '<script type="application/json" id="ledger-data">'
BLOCK_CLOSE = "</script>"
#: Most lines `diff_summary` prints before truncating (plus one trailer line).
DIFF_MAX_LINES = 30


def _dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _ordered(item: dict, keys: tuple[str, ...]) -> dict:
    """`item` with `keys` first, in contract order; any other keys after."""
    head = {k: item[k] for k in keys if k in item}
    return {**head, **{k: v for k, v in item.items() if k not in head}}


def _dump_list(items: list, keys: tuple[str, ...]) -> str:
    """One item per line, two-space indent; `[]` when empty."""
    if not items:
        return "[]"
    return "[\n" + ",\n".join("  " + _dumps(_ordered(i, keys)) for i in items) + "\n]"


def render_block(data: dict) -> str:
    """The `ledger-data` JSON text: deterministic, diff-friendly, HTML-safe.

    Layout: scalar top-level keys on the first line, then one feature per line
    and one audit entry per line. `ensure_ascii=False` keeps `→` / CJK
    readable; default separators; fixed key order.

    HTML safety is a post-serialisation escape. `<` only ever occurs inside
    JSON strings, so both replacements stay valid JSON and round-trip:
    `</` -> `<\\/` (covers `</script` in any case, so the first `</script>`
    after the opening tag is always the true block end) and `<!--` ->
    `\\u003c!--` (`<\\!--` would be an invalid JSON escape).
    """
    parts = []
    for key in TOP_KEYS:
        value = data.get(key)
        if key == "features":
            text = _dump_list(value or [], FEATURE_KEYS)
        elif key == "audit":
            text = _dump_list(value or [], AUDIT_KEYS)
        else:
            text = _dumps(value)
        parts.append(f"{_dumps(key)}: {text}")
    raw = "{" + ", ".join(parts) + "}"
    return raw.replace("</", "<\\/").replace("<!--", "\\u003c!--")


def splice(html: str, block: str) -> tuple[str, list[str]]:
    """Replace only the interior of the single `ledger-data` block.

    Returns `(new_html, errors)`; on error `new_html` is `html` unchanged and
    `errors` is non-empty. The interior becomes `"\\n" + block + "\\n"` (the
    committed page's form), so splicing the same block twice is a no-op.
    Every byte before the opening tag and from the closing `</script>` on is
    kept as is.
    """
    count = html.count(BLOCK_OPEN)
    if count != 1:
        return html, [
            f"feature-ledger.html: expected exactly one `{BLOCK_OPEN}` "
            f"(ledger-data block), found {count}."
        ]
    start = html.index(BLOCK_OPEN) + len(BLOCK_OPEN)
    end = html.find(BLOCK_CLOSE, start)
    if end < 0:
        return html, [f"feature-ledger.html: the ledger-data block has no closing `{BLOCK_CLOSE}`."]
    return html[:start] + "\n" + block + "\n" + html[end:], []


def diff_summary(old: str, new: str) -> str:
    """A short unified-diff excerpt of `old` -> `new`; `""` when identical."""
    if old == new:
        return ""
    lines = list(
        difflib.unified_diff(
            old.splitlines(), new.splitlines(), "committed", "generated", n=2, lineterm=""
        )
    )
    if len(lines) > DIFF_MAX_LINES:
        more = len(lines) - DIFF_MAX_LINES
        lines = lines[:DIFF_MAX_LINES] + [f"... ({more} more diff lines)"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# WI-7: CLI
# ---------------------------------------------------------------------------


#: Repo-relative inputs, and the command every drift message tells you to run.
MD_REL = SYNCED_FROM
HTML_REL = "docs/feature-ledger.html"
BUILD_COMMAND = "python3 scripts/build_feature_ledger.py"


def _read(root: Path, rel: str, errors: list[str]) -> str | None:
    """File text, or `None` with an error naming the file (never a traceback).

    `newline=""` keeps the bytes exactly: a `--check` must see what is
    committed, and a build must leave every byte outside the block alone.
    """
    try:
        with open(root / rel, encoding="utf-8", newline="") as fh:
            return fh.read()
    except FileNotFoundError:
        errors.append(f"{rel}: file not found under {root}.")
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"{rel}: cannot read ({exc}).")
    return None


def _report(title: str, lines: list[str]) -> None:
    print(f"\n{title}", file=sys.stderr)
    for line in lines:
        print("  - " + line, file=sys.stderr)


def run(repo_root: Path, check: bool) -> int:
    """Build (write the block) or `--check` (validate + compare, never write).

    Both modes run the full pipeline — parse, every validator, splice — so
    `--check` fails on an invalid repo even when the committed block happens
    to equal the rendered one. The build writes only when that pipeline has
    zero errors; otherwise the HTML bytes stay as they were.
    """
    root = Path(repo_root).resolve()
    errors: list[str] = []
    md = _read(root, MD_REL, errors)
    html = _read(root, HTML_REL, errors)
    new_html = None
    if md is not None:
        data, validation_errors = validate(md, root)
        errors += validation_errors
        if html is not None:
            new_html, splice_errors = splice(html, render_block(data))
            errors += splice_errors
    if errors or new_html is None or html is None:
        _report(f"feature ledger: {len(errors)} error(s) in {MD_REL} / {HTML_REL}:", errors)
        print(f"\nNothing written. Fix the errors, then run `{BUILD_COMMAND}`.", file=sys.stderr)
        return 1

    if check:
        if new_html != html:
            print(
                f"\nfeature ledger drift: the ledger-data block in {HTML_REL} does not match "
                f"{MD_REL}.\n{diff_summary(html, new_html)}\n"
                f"\nFix: run `{BUILD_COMMAND}` and commit {HTML_REL}.",
                file=sys.stderr,
            )
            return 1
        print(f"feature ledger in sync: {HTML_REL} matches {MD_REL}.")
        return 0

    if new_html != html:
        with open(root / HTML_REL, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new_html)
        print(f"feature ledger built: {HTML_REL} regenerated from {MD_REL}.")
    else:
        print(f"feature ledger unchanged: {HTML_REL} already matches {MD_REL}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=f"Generate the ledger-data block of {HTML_REL} from {MD_REL}."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate and compare only; exit 1 on any error or drift; never write",
    )
    parser.add_argument(
        "--root", type=Path, default=REPO_ROOT, help="repo root (default: this script's repo)"
    )
    args = parser.parse_args(argv)
    return run(args.root, args.check)


if __name__ == "__main__":
    sys.exit(main())

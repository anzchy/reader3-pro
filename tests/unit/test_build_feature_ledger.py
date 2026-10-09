"""`scripts/build_feature_ledger.py` must turn `docs/feature-ledger.md` into the
`ledger-data` JSON block, and must say *every* reason it cannot.

The md is the single source; the HTML dashboard is a view of it. Before this
script the view was hand-mirrored, so the two drifted silently. The parser is
therefore strict: anything it cannot read exactly is an error, never a guess.

The script is not a package; it is loaded from its path with
`importlib.util.spec_from_file_location`, like `test_router_size_gate.py`.

Test-side helpers (`load`, `md_doc`) live here and never import from the
script, so no oracle is circular.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_feature_ledger.py"

TOP_KEYS = ["synced_from", "synced_at", "commit", "statuses", "features", "audit"]
STATUSES = [
    "accepted",
    "partial",
    "stub",
    "absent",
    "unknown",
    "deprecated",
    "superseded",
    "removed",
]
SUMMARY_HEADER = "| ID | Feature | Area | Status | Evidence |"
LABEL_ORDER = ("What", "Routes", "Code", "Tests", "Confirm", "Tracked", "Evidence", "Limits")


def load():
    spec = importlib.util.spec_from_file_location("build_feature_ledger_under_test", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {SCRIPT_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script():
    return load()


# ---------------------------------------------------------------------------
# md printer
# ---------------------------------------------------------------------------

DEFAULT_FEATURE = {
    "id": "F-001",
    "name": "EPUB ingest CLI",
    "area": "EPUB processing",
    "status": "accepted",
    "bullets": {
        "What": "Parses an EPUB.",
        "Routes": "`cli: reader3`",
        "Code": "`src/reader3_app/reader3.py`",
        "Tests": "`tests/unit/test_process_epub_commit.py`",
        "Confirm": "Run `uv run reader3 ./books/dracula.epub`.",
        "Evidence": "v1.0 · baseline",
    },
}

DEFAULT_AUDIT = {
    "date": "2026-09-27",
    "title": "Baseline seed",
    "commit": "8e1cf48",
    "scope": "rows seeded",
    "found": "—",
    "not_audited": "no lane run",
}


#: Refs an `absent` row's Summary cell may track: a debt `#N`, else a plan / branch `NNN`.
_TRACKED_DEBT_RE = re.compile(r"(?<!\d)#\d+")
_TRACKED_BRANCH_RE = re.compile(r"(?<!\d)\d{3}(?!\d)")


def summary_evidence(f):
    """The Summary Evidence cell `md_doc` prints for an `md_doc` feature.

    Non-absent rows reuse the section's Evidence bullet (the cell is its short
    form). An `absent` row has no Evidence bullet; its cell is `tracked <refs>`
    built from its Tracked bullet, or `""` when that carries no ref.
    """
    if f["status"].split()[:1] != ["absent"]:
        return f["bullets"].get("Evidence", "")
    tracked = f["bullets"].get("Tracked", "")
    refs = _TRACKED_DEBT_RE.findall(tracked) or _TRACKED_BRANCH_RE.findall(tracked)
    return "tracked " + " · ".join(dict.fromkeys(refs)) if refs else ""


def md_doc(
    features=None,
    audit=None,
    synced=("2026-09-27", "8e1cf48"),
    summary=None,
    preamble=None,
    audit_intro=None,
    trailer=None,
):
    """Print a ledger md. `synced=None` omits the Synced line; `summary`
    replaces the Summary table rows (list of raw lines after the separator)."""
    features = [DEFAULT_FEATURE] if features is None else features
    audit = [DEFAULT_AUDIT] if audit is None else audit
    out = ["# Feature Ledger", ""]
    if synced is not None:
        out += [f"**Synced:** {synced[0]} at commit `{synced[1]}`", ""]
    out += ["The as-built record.", "", "## Rules", "", "1. Rules text.", ""]
    out += ["## Summary", "", SUMMARY_HEADER, "|---|---|---|---|---|"]
    if summary is None:
        for f in features:
            ev = summary_evidence(f)
            out.append(f"| {f['id']} | {f['name']} | {f['area']} | {f['status']} | {ev} |")
    else:
        out += list(summary)
    out += ["", "## Features", ""]
    if preamble is not None:
        out += [preamble, ""]
    last_area = None
    for f in features:
        if f["area"] != last_area:
            out += [f"### {f['area']}", ""]
            last_area = f["area"]
        out.append(f"#### {f['id']} {f['name']} — {f['status']}")
        for label in LABEL_ORDER:
            if label in f["bullets"]:
                out.append(f"- **{label}:** {f['bullets'][label]}")
        out.append("")
    out += ["## Audit log", ""]
    if audit_intro is not None:
        out += [audit_intro, ""]
    for a in audit:
        out.append(f"### {a['date']} — {a['title']} (`{a['commit']}`)")
        out.append(f"- **Scope:** {a['scope']}")
        out.append(f"- **Found:** {a['found']}")
        out.append(f"- **Not audited:** {a['not_audited']}")
        out.append("")
    if trailer is not None:
        out += list(trailer)
    return "\n".join(out) + "\n"


def _two_features():
    second = {
        "id": "F-002",
        "name": "Semantic index CLI",
        "area": "EPUB processing",
        "status": "accepted",
        "bullets": dict(DEFAULT_FEATURE["bullets"]),
    }
    return [DEFAULT_FEATURE, second]


# ---------------------------------------------------------------------------
# WI-1: document skeleton
# ---------------------------------------------------------------------------


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    d=st.dates(min_value=date(2000, 1, 1), max_value=date(2099, 12, 31)),
    c=st.text("0123456789abcdef", min_size=7, max_size=40),
)
def test_u1_p1_synced_round_trips(script, d, c):
    audit = [dict(DEFAULT_AUDIT, date=d.isoformat())]
    data, errors = script.parse_ledger(md_doc(audit=audit, synced=(d.isoformat(), c)))
    assert errors == []
    assert (data["synced_at"], data["commit"]) == (d.isoformat(), c)
    assert list(data) == TOP_KEYS
    assert data["statuses"] == STATUSES


def test_u1_s1_minimal_valid_md_exact_top_level_shape(script):
    data, errors = script.parse_ledger(md_doc())
    assert errors == []
    assert list(data) == TOP_KEYS
    assert data["synced_from"] == "docs/feature-ledger.md"
    assert data["statuses"] == STATUSES
    assert (data["synced_at"], data["commit"]) == ("2026-09-27", "8e1cf48")


SYNCED_OK = "**Synced:** 2026-09-27 at commit `8e1cf48`"


def _synced_defects():
    base = md_doc()
    return {
        "missing": base.replace(SYNCED_OK + "\n", ""),
        "duplicated": base.replace(SYNCED_OK, SYNCED_OK + "\n" + SYNCED_OK),
        "short-date": base.replace("2026-09-27 at", "2026-9-27 at"),
        "impossible-date": base.replace("2026-09-27 at", "2026-02-30 at"),
        "non-hex": base.replace("`8e1cf48`", "`XYZ1234`"),
        "uppercase-hex": base.replace("`8e1cf48`", "`8E1CF48`"),
        "six-chars": base.replace("`8e1cf48`", "`8e1cf4`"),
        "41-chars": base.replace("`8e1cf48`", "`" + "a" * 41 + "`"),
        "below-intro": base.replace(SYNCED_OK + "\n\n", "").replace(
            "The as-built record.\n", "The as-built record.\n\n" + SYNCED_OK + "\n"
        ),
        "no-h1": base.replace("# Feature Ledger\n", "", 1),
    }


@pytest.mark.parametrize("case", list(_synced_defects()))
def test_u1_f1_synced_defect_gives_exactly_one_synced_error(script, case):
    md = _synced_defects()[case]
    assert md != md_doc(), f"fixture for {case!r} did not change the md"
    _, errors = script.parse_ledger(md)
    synced_errors = [e for e in errors if "Synced" in e]
    assert len(synced_errors) == 1, errors


@pytest.mark.parametrize("sha", ["a1b2c3d", "0123456789abcdef0123456789abcdef01234567"])
def test_u1_b1_synced_sha_length_edges(script, sha):
    data, errors = script.parse_ledger(md_doc(synced=("2026-09-27", sha)))
    assert errors == []
    assert data["commit"] == sha


ROW1 = "| F-001 | EPUB ingest CLI | EPUB processing | accepted | v1.0 · baseline |"


def test_u1_f2a_summary_missing(script):
    md = md_doc().replace("## Summary\n", "")
    _, errors = script.parse_ledger(md)
    assert any("Summary" in e for e in errors), errors


def test_u1_f2b_summary_wrong_header(script):
    md = md_doc().replace(SUMMARY_HEADER, "| ID | Name | Area | Status | Evidence |")
    _, errors = script.parse_ledger(md)
    assert any("Summary" in e for e in errors), errors


@pytest.mark.parametrize(
    "row",
    [
        "| F-002 | Semantic index CLI | EPUB processing | accepted |",
        "| F-002 | A | B | EPUB processing | accepted | baseline |",
        "| F-002 | A \\| B | EPUB processing | accepted | baseline |",
    ],
    ids=["four-cells", "pipe-in-cell", "escaped-pipe"],
)
def test_u1_f2cde_summary_row_defect_names_row_id(script, row):
    data, errors = script.parse_ledger(md_doc(summary=[ROW1, row]))
    assert any("F-002" in e for e in errors), errors
    names = [f.get("name") for f in data.get("features", [])]
    assert "A" not in names and "B" not in names


def test_u1_f2f_summary_zero_rows(script):
    _, errors = script.parse_ledger(md_doc(summary=[]))
    assert any("Summary" in e for e in errors), errors


def test_u1_f2_valid_summary_has_no_summary_error(script):
    # Kill-pair anchor for U1-F2: the same printer with a well-formed table is clean.
    _, errors = script.parse_ledger(md_doc(features=_two_features()))
    assert errors == []


def test_u1_f3a_features_heading_missing(script):
    md = md_doc().replace("## Features\n", "")
    _, errors = script.parse_ledger(md)
    assert any("Features" in e for e in errors), errors


def test_u1_f3b_audit_log_section_missing(script):
    md = md_doc(audit=[]).replace("## Audit log\n", "")
    _, errors = script.parse_ledger(md)
    assert any("Audit log" in e for e in errors), errors


CHECKLIST = [
    "## Update checklist (after a module is accepted)",
    "",
    "1. Gating lanes green on `master`.",
    "2. New capability → append a row to **Summary**.",
    "8. Mirror the change into the `ledger-data` JSON block.",
]


def test_u1_b2_checklist_trailer_raises_no_error(script):
    _, errors = script.parse_ledger(md_doc(trailer=CHECKLIST))
    assert errors == []


def test_u1_b2_features_section_ends_at_audit_log(script):
    ghost = ["#### F-099 Ghost — accepted", "- **What:** x", ""]
    md = md_doc(trailer=ghost + CHECKLIST)
    # The ghost sits after the audit entry, i.e. inside `## Audit log`.
    assert md.index("#### F-099") > md.index("## Audit log")
    data, errors = script.parse_ledger(md)
    ids = [f["id"] for f in data["features"]]
    assert "F-099" not in ids
    sections = script.split_sections(md)
    features_body = "\n".join(sections["Features"])
    audit_body = "\n".join(sections["Audit log"])
    assert "F-099" not in features_body
    assert "F-001" in features_body
    assert "#### F-099 Ghost — accepted" in audit_body
    assert "Gating lanes" not in audit_body
    assert not any("1." in e or "Gating" in e for e in errors), errors


def test_u1_b2_features_are_only_the_summary_rows(script):
    # Deferred WI-1 assertion (U1-B2): with the ghost under `## Audit log`,
    # the feature list is exactly the Summary's one row.
    ghost = ["#### F-099 Ghost — accepted", "- **What:** x", ""]
    data, _ = script.parse_ledger(md_doc(trailer=ghost + CHECKLIST))
    assert [f["id"] for f in data["features"]] == ["F-001"]


# ---------------------------------------------------------------------------
# WI-2: feature sections -> feature dicts
# ---------------------------------------------------------------------------

KEY_ORDER = [
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
]

REQ, OPT, FORBID = "required", "optional", "forbidden"
#: The md's Row grammar table plus the orchestrator's `removed` row,
#: hand-transcribed; never read from the script.
_ROW_ACCEPTED = dict(
    What=REQ, Routes=OPT, Code=REQ, Tests=REQ, Confirm=REQ, Tracked=FORBID, Evidence=REQ, Limits=OPT
)
_ROW_STUB = dict(_ROW_ACCEPTED, Tests=OPT)
_ROW_ABSENT = dict(
    What=REQ, Routes=OPT, Code=FORBID, Tests=FORBID, Confirm=FORBID, Tracked=REQ, Evidence=FORBID, Limits=OPT
)
_ROW_RETIRED = dict(_ROW_ACCEPTED, Tests=OPT, Confirm=OPT)
_ROW_REMOVED = dict(_ROW_RETIRED, Code=FORBID, Tests=FORBID)
GRAMMAR_ORACLE = {
    "accepted": _ROW_ACCEPTED,
    "partial": _ROW_ACCEPTED,
    "stub": _ROW_STUB,
    "unknown": _ROW_STUB,
    "absent": _ROW_ABSENT,
    "deprecated": _ROW_RETIRED,
    "superseded": _ROW_RETIRED,
    "removed": _ROW_REMOVED,
}

_LABEL_KEY = {
    "What": "what",
    "Routes": "routes",
    "Code": "code",
    "Tests": "tests",
    "Confirm": "confirm",
    "Tracked": "tracked",
    "Evidence": "evidence",
    "Limits": "limits",
}


def _render_path(entry):
    # "path (note)" -> "`path` (note)"; path characters never include a space.
    path, sep, rest = entry.partition(" (")
    return f"`{path}`" + (f" ({rest}" if sep else "")


def md_feature(f):
    """JSON-shape feature dict -> the `md_doc` feature shape."""
    bullets = {}
    for label in LABEL_ORDER:
        value = f[_LABEL_KEY[label]]
        if label == "Routes" and value:
            bullets[label] = ", ".join(f"`{r}`" for r in value)
        elif label == "Code" and value:
            text = ", ".join(_render_path(p) for p in value)
            if f["adr"]:
                text += " · " + ", ".join(f["adr"])
            bullets[label] = text
        elif label == "Tests" and value:
            bullets[label] = ", ".join(_render_path(p) for p in value)
        elif isinstance(value, str) and value:
            bullets[label] = value
    return {"id": f["id"], "name": f["name"], "area": f["area"], "status": f["status"], "bullets": bullets}


def summary_rows(md_features):
    return [
        f"| {f['id']} | {f['name']} | {f['area']} | {f['status']} | {summary_evidence(f)} |"
        for f in md_features
    ]


_TEXT_ALPHABET = "abcXYZ019 `→é「」\";,.:()#*-/'"
st_line = (
    st.text(_TEXT_ALPHABET, min_size=1, max_size=30)
    .map(str.strip)
    .filter(lambda s: s != "" and "  " not in s)
)
_PATH_CHARS = "abcz019_./-"
_note_part = st.one_of(
    st.text("abc XYZ;,é", min_size=1, max_size=10),
    st.text("abc_*.", min_size=1, max_size=6).map(lambda s: f"`{s}`"),
)
st_note = st.lists(_note_part, min_size=1, max_size=4).map("".join).map(str.strip).filter(bool)
st_paths = st.builds(
    lambda p, note: p if note is None else f"{p} ({note})",
    st.text(_PATH_CHARS, min_size=1, max_size=20).filter(lambda s: not s.startswith("/")),
    st.none() | st_note,
)
st_routes = st.one_of(
    st.sampled_from(["cli: reader3", "cli: reader3-server", "GET /", "MOUNT /static"]),
    st.builds(
        lambda m, p: f"{m} /{p}",
        st.sampled_from(["GET", "POST", "PUT", "DELETE"]),
        st.text("abc/{}_-", max_size=15),
    ),
)
st_adr = st.from_regex(r"ADR-\d{4}", fullmatch=True)
#: One evidence token, rendered: `PR #N`, a backticked SHA (≥ 1 letter a–f),
#: a `vX.Y` / `vX.Y.Z` tag, or `baseline` (Rule 7).
st_ev_token = st.one_of(
    st.integers(1, 99).map(lambda n: f"PR #{n}"),
    st.from_regex(r"[0-9a-f]{6,38}[a-f][0-9a-f]?", fullmatch=True).map(lambda s: f"`{s}`"),
    st.from_regex(r"v[0-9]{1,2}\.[0-9]{1,2}(\.[0-9]{1,2})?", fullmatch=True),
    st.just("baseline"),
)
#: A valid Evidence value: optional context, then ≥ 1 token, joined by ` · `.
st_evidence = st.builds(
    lambda ctx, tokens: " · ".join(([ctx] if ctx else []) + tokens),
    st.none() | st.sampled_from(["004", "011/017", "013 WI-9", "ADR-0006", "debt #21"]),
    st.lists(st_ev_token, min_size=1, max_size=3),
)
#: A valid Tracked value: always carries a debt `#N` the Summary cell can track.
st_tracked = st.builds(
    lambda n, rest: f"debt #{n}" + (f" {rest}" if rest else ""),
    st.integers(1, 999),
    st.none() | st_line,
)


@st.composite
def st_features(draw, min_size=1, max_size=6):
    n = draw(st.integers(min_size, max_size))
    ids = [f"F-{i:03d}" for i in range(1, n + 1)]
    out = []
    for fid in ids:
        base = draw(st.sampled_from(STATUSES))
        others = [x for x in ids if x != fid]
        if base == "superseded" and not others:
            base = "deprecated"
        status = f"superseded → {draw(st.sampled_from(others))}" if base == "superseded" else base
        rules = GRAMMAR_ORACLE[base]

        def present(label, rules=rules):
            rule = rules[label]
            return rule == REQ or (rule == OPT and draw(st.booleans()))

        f = {
            "id": fid,
            "name": draw(st_line),
            "area": draw(st_line),
            "status": status,
            "what": draw(st_line),
            "routes": draw(st.lists(st_routes, min_size=1, max_size=3)) if present("Routes") else [],
            "code": draw(st.lists(st_paths, min_size=1, max_size=3)) if present("Code") else [],
            "tests": draw(st.lists(st_paths, min_size=1, max_size=3)) if present("Tests") else [],
            "adr": [],
            "confirm": draw(st_line) if present("Confirm") else "",
            "tracked": draw(st_tracked) if present("Tracked") else "",
            "evidence": draw(st_evidence) if present("Evidence") else "",
            "limits": draw(st_line) if present("Limits") else "",
        }
        if f["code"]:
            f["adr"] = draw(st.lists(st_adr, max_size=3))
        out.append(f)
    return out


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(features=st_features())
def test_u2_p1_md_round_trip(script, features):
    data, errors = script.parse_ledger(md_doc(features=[md_feature(f) for f in features]))
    assert errors == []
    assert data["features"] == features
    assert [list(f) for f in data["features"]] == [KEY_ORDER] * len(features)


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data_=st.data())
def test_u2_p2_section_order_does_not_affect_output(script, data_):
    features = data_.draw(st_features(min_size=2, max_size=6))
    perm = data_.draw(st.permutations(range(len(features))))
    md_features = [md_feature(f) for f in features]
    rows = summary_rows(md_features)
    canonical, _ = script.parse_ledger(md_doc(features=md_features, summary=rows))
    permuted, _ = script.parse_ledger(md_doc(features=[md_features[i] for i in perm], summary=rows))
    assert permuted["features"] == canonical["features"]
    assert [f["id"] for f in permuted["features"]] == [f["id"] for f in features]


def _feat(fid, name, status, area="EPUB processing", **bullets):
    return {"id": fid, "name": name, "area": area, "status": status, "bullets": bullets}


def test_u2_s1_three_feature_fixture_exact(script):
    features = [
        _feat(
            "F-001",
            "Library",
            "accepted",
            What="The library page.",
            Routes="`GET /`, `MOUNT /static`",
            Code="`a.py`, `b/` · ADR-0010, ADR-0011",
            Tests="`tests/unit/` (`test_book_uuid_*`)",
            Confirm="Open `/`.",
            Evidence="004 · baseline",
            Limits="debt #18.",
        ),
        _feat(
            "F-002",
            "Paper themes",
            "stub",
            area="Reader",
            What="Theme swatches.",
            Code="`c.js`",
            Confirm="Click a swatch: nothing happens.",
            Evidence="013 · baseline",
        ),
        _feat("F-003", "Book delete", "absent", area="Reader", What="No delete.", Tracked="debt #58, 012"),
    ]
    data, errors = script.parse_ledger(md_doc(features=features))
    assert errors == []
    assert data["features"] == [
        {
            "id": "F-001",
            "name": "Library",
            "area": "EPUB processing",
            "status": "accepted",
            "what": "The library page.",
            "routes": ["GET /", "MOUNT /static"],
            "code": ["a.py", "b/"],
            "tests": ["tests/unit/ (`test_book_uuid_*`)"],
            "adr": ["ADR-0010", "ADR-0011"],
            "confirm": "Open `/`.",
            "tracked": "",
            "evidence": "004 · baseline",
            "limits": "debt #18.",
        },
        {
            "id": "F-002",
            "name": "Paper themes",
            "area": "Reader",
            "status": "stub",
            "what": "Theme swatches.",
            "routes": [],
            "code": ["c.js"],
            "tests": [],
            "adr": [],
            "confirm": "Click a swatch: nothing happens.",
            "tracked": "",
            "evidence": "013 · baseline",
            "limits": "",
        },
        {
            "id": "F-003",
            "name": "Book delete",
            "area": "Reader",
            "status": "absent",
            "what": "No delete.",
            "routes": [],
            "code": [],
            "tests": [],
            "adr": [],
            "confirm": "",
            "tracked": "debt #58, 012",
            "evidence": "",
            "limits": "",
        },
    ]
    assert [list(f) for f in data["features"]] == [KEY_ORDER] * 3


def _with_f2(**bullet_overrides):
    """Two-feature md where F-002's bullets are overridden (None drops one)."""
    features = _two_features()
    bullets = dict(features[1]["bullets"])
    for label, value in bullet_overrides.items():
        if value is None:
            bullets.pop(label, None)
        else:
            bullets[label] = value
    features[1] = dict(features[1], bullets=bullets)
    return md_doc(features=features)


def _f2(data):
    return next(f for f in data["features"] if f["id"] == "F-002")


@pytest.mark.parametrize(
    "value, expected",
    [
        (
            "`x.py` (pins that clicking does not break annotations; cannot assert a theme change)",
            ["x.py (pins that clicking does not break annotations; cannot assert a theme change)"],
        ),
        ("`a.py` (covers A, not B), `b.py` (`test_*`)", ["a.py (covers A, not B)", "b.py (`test_*`)"]),
    ],
    ids=["semicolon-note", "two-noted-entries"],
)
def test_u2_b1_notes_stay_whole(script, value, expected):
    data, errors = script.parse_ledger(_with_f2(Tests=value))
    assert errors == []
    assert _f2(data)["tests"] == expected


@pytest.mark.parametrize(
    "value, code, adr",
    [
        ("`a.py` · ADR-0007", ["a.py"], ["ADR-0007"]),
        ("`a.py`, `b.py`", ["a.py", "b.py"], []),
    ],
    ids=["one-adr", "no-adr"],
)
def test_u2_b2_adr_split(script, value, code, adr):
    data, errors = script.parse_ledger(_with_f2(Code=value))
    assert errors == []
    assert (_f2(data)["code"], _f2(data)["adr"]) == (code, adr)


def test_u2_b2_routes_with_cli_entry(script):
    data, errors = script.parse_ledger(_with_f2(Routes="`cli: reader3`, `GET /api/x/{book_id}`"))
    assert errors == []
    assert _f2(data)["routes"] == ["cli: reader3", "GET /api/x/{book_id}"]


def test_u2_b3_em_dash_name_and_arrow_status(script):
    bullets = dict(DEFAULT_FEATURE["bullets"])
    features = [
        _feat("F-001", "Import — legacy path", "accepted", **bullets),
        _feat("F-002", "Old", "superseded → F-001", **bullets),
    ]
    data, errors = script.parse_ledger(md_doc(features=features))
    assert errors == []
    f1, f2 = data["features"]
    assert (f1["name"], f1["status"]) == ("Import — legacy path", "accepted")
    assert (f2["name"], f2["status"]) == ("Old", "superseded → F-001")


def test_u2_b4_features_preamble_and_area_prose_ignored(script):
    bullets = dict(DEFAULT_FEATURE["bullets"])
    features = [
        _feat("F-001", "Ingest", "accepted", **bullets),
        _feat("F-002", "Pager", "accepted", area="Reader", **bullets),
    ]
    preamble = (
        "Paths are relative to the repo root; `src/` = `src/reader3_app/`, `e2e/` = `tests/e2e/`."
        "\n\nSome other note."
    )
    md = md_doc(features=features, preamble=preamble)
    md = md.replace("### EPUB processing\n", "### EPUB processing\n\nProse under the area heading.\n", 1)
    assert "Prose under the area heading." in md and "### Reader" in md
    data, errors = script.parse_ledger(md)
    assert errors == []
    assert [f["id"] for f in data["features"]] == ["F-001", "F-002"]
    blob = repr(data["features"])
    for text in ("Paths are relative", "Some other note", "Prose under"):
        assert text not in blob


@pytest.mark.parametrize(
    "label, bad, good",
    [
        ("Code", "`a.py", "`a.py`"),
        ("Code", "`a.py` `b.py`", "`a.py`, `b.py`"),
        ("Code", "`a.py` junk", "`a.py` (junk)"),
        ("Code", "`a.py` · ADR-7", "`a.py` · ADR-0007"),
        ("Code", "· ADR-0007", "`a.py` · ADR-0007"),
        ("Routes", "`GET /` GET /x", "`GET /`, `GET /x`"),
        ("Tests", "`a.py` (unclosed", "`a.py` (unclosed)"),
    ],
    ids=["unbalanced-backtick", "missing-comma", "trailing-junk", "bad-adr", "adr-without-path", "routes-junk", "unclosed-note"],
)
def test_u2_f1_unconsumable_value_kill_pair(script, label, bad, good):
    _, errors = script.parse_ledger(_with_f2(**{label: bad}))
    assert any("F-002" in e and label in e for e in errors), errors
    _, errors = script.parse_ledger(_with_f2(**{label: good}))
    assert not any("F-002" in e for e in errors), errors


_WHAT_LINE = "- **What:** Parses an EPUB."


def _f2_section_edit(md, old, new):
    head = "#### F-002 Semantic index CLI — accepted\n"
    start = md.index(head)
    end = md.index("\n\n", start)
    section = md[start:end]
    assert old in section
    return md[:start] + section.replace(old, new, 1) + md[end:]


def _bullet_defects():
    base = md_doc(features=_two_features())
    return {
        "unknown-label": _f2_section_edit(base, _WHAT_LINE, _WHAT_LINE + "\n- **Limit:** x"),
        "duplicate-label": _f2_section_edit(base, _WHAT_LINE, _WHAT_LINE + "\n- **What:** again"),
        "continuation-line": _f2_section_edit(base, _WHAT_LINE, _WHAT_LINE + "\n  more text"),
        "prose-between-bullets": _f2_section_edit(base, _WHAT_LINE, _WHAT_LINE + "\nSome prose."),
        "empty-value": _f2_section_edit(base, _WHAT_LINE, "- **What:**"),
        "hyphen-heading": base.replace(
            "#### F-002 Semantic index CLI — accepted", "#### F-002 Foo - accepted"
        ),
    }


@pytest.mark.parametrize("case", list(_bullet_defects()))
def test_u2_f2_bullet_structure_defect_names_feature(script, case):
    md = _bullet_defects()[case]
    assert md != md_doc(features=_two_features())
    _, errors = script.parse_ledger(md)
    assert any("F-002" in e for e in errors), errors
    if case == "hyphen-heading":
        assert any("F-002 Foo - accepted" in e for e in errors), errors


def test_u2_s2_evidence_from_section_not_summary(script):
    f = _feat(
        "F-001",
        "Publish",
        "partial",
        What="Stage and swap.",
        Code="`a.py`",
        Tests="`t.py`",
        Confirm="Re-run.",
        Evidence="007 · PR #26 (`b8e0353`)",
    )
    row = "| F-001 | Publish | EPUB processing | partial | 007 · PR #26 |"
    data, errors = script.parse_ledger(md_doc(features=[f], summary=[row]))
    assert errors == []
    assert data["features"][0]["evidence"] == "007 · PR #26 (`b8e0353`)"


# ---------------------------------------------------------------------------
# WI-3: row grammar + cross-row validation
# ---------------------------------------------------------------------------
#
# `row_errors(md)` runs only the row-grammar stage, so parse-stage errors
# never leak into these assertions; `script.validate(md)` is the aggregated
# pipeline (parse + rows) and is pinned separately.

#: One well-formed value per label, used to build label subsets.
LABEL_VALUES = {
    "What": "Does a thing.",
    "Routes": "`GET /`",
    "Code": "`a.py`",
    "Tests": "`t.py`",
    "Confirm": "Run it.",
    "Tracked": "debt #58",
    "Evidence": "004 · baseline",
    "Limits": "none known.",
}


def row_errors(script, md):
    doc, _ = script.parse_document(md)
    return script.validate_rows(doc)


def _required(base):
    return [label for label in LABEL_ORDER if GRAMMAR_ORACLE[base][label] == REQ]


def _row(fid, name, status, labels, area="EPUB processing"):
    return _feat(fid, name, status, area=area, **{label: LABEL_VALUES[label] for label in labels})


def _anchor():
    """F-001: an always-valid accepted row (superseded targets point at it)."""
    return _row("F-001", "Anchor", "accepted", _required("accepted"))


def _status_for(base):
    return "superseded → F-001" if base == "superseded" else base


def _labels_mentioned(label, fid, base, errors):
    return any(label in e and fid in e and base in e for e in errors)


def test_u3_p1_exhaustive_grammar_vs_oracle(script):
    failures = []
    for base in STATUSES:
        for mask in range(2 ** len(LABEL_ORDER)):
            labels = [label for i, label in enumerate(LABEL_ORDER) if mask >> i & 1]
            rules = GRAMMAR_ORACLE[base]
            missing = [x for x in LABEL_ORDER if rules[x] == REQ and x not in labels]
            forbidden = [x for x in labels if rules[x] == FORBID]
            md = md_doc(features=[_anchor(), _row("F-002", "Under test", _status_for(base), labels)])
            errors = row_errors(script, md)
            if not missing and not forbidden:
                if any("F-002" in e for e in errors):
                    failures.append((base, labels, "expected clean", errors))
            else:
                unnamed = [x for x in missing + forbidden if not _labels_mentioned(x, "F-002", base, errors)]
                if unnamed:
                    failures.append((base, labels, f"not reported: {unnamed}", errors))
    assert failures == [], f"{len(failures)} combinations disagree with the oracle; first: {failures[:3]}"


_ROW0 = {
    "name": "0", "area": "0", "what": "0", "routes": [], "adr": [], "tracked": "", "limits": "",
}


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(features=st_features(min_size=1, max_size=8))
# A digit glued to `#` (`0#0`) is not a ref to the script; the oracle once read it as `#0`.
@example(
    features=[
        dict(_ROW0, id="F-001", status="accepted", code=["0"], tests=["0"], confirm="0", evidence="PR #1"),
        dict(_ROW0, id="F-002", status="accepted", code=["0"], tests=["0"], confirm="0", evidence="baseline"),
        dict(_ROW0, id="F-003", status="absent", code=[], tests=[], confirm="", evidence="", tracked="debt #1 0#0"),
    ]
)
def test_u3_p2_grammar_conforming_ledgers_validate_clean(script, features):
    assert row_errors(script, md_doc(features=[md_feature(f) for f in features])) == []


_S1_CASES = [
    # (base, add, drop, expect_error, label named)
    ("absent", ["Code"], [], True, "Code"),
    ("absent", ["Evidence"], [], True, "Evidence"),
    ("accepted", ["Tracked"], [], True, "Tracked"),
    ("removed", ["Code"], [], True, "Code"),
    ("removed", ["Tests"], [], True, "Tests"),
    ("removed", [], ["Evidence"], True, "Evidence"),
    ("stub", [], ["Tests"], False, "Tests"),
    ("unknown", [], ["Tests"], False, "Tests"),
    ("deprecated", [], ["Confirm"], False, "Confirm"),
    ("deprecated", [], ["Code"], True, "Code"),
]


@pytest.mark.parametrize(
    "base, add, drop, expect_error, label",
    _S1_CASES,
    ids=[f"{b}{'+' + a[0] if a else ''}{'-' + d[0] if d else ''}" for b, a, d, _, _ in _S1_CASES],
)
def test_u3_s1_named_cells_of_the_table(script, base, add, drop, expect_error, label):
    # Start from every label the oracle allows (required + optional), so the
    # only change from a clean row is the one under test.
    allowed = [x for x in LABEL_ORDER if GRAMMAR_ORACLE[base][x] != FORBID]
    labels = [x for x in LABEL_ORDER if (x in allowed or x in add) and x not in drop]
    md = md_doc(features=[_anchor(), _row("F-002", "Under test", _status_for(base), labels)])
    errors = row_errors(script, md)
    if expect_error:
        assert _labels_mentioned(label, "F-002", base, errors), errors
    else:
        assert errors == []


#: Per status: one required label to drop and one forbidden label to add.
_KILL_PAIRS = {
    "accepted": ("Tests", "Tracked"),
    "partial": ("Confirm", "Tracked"),
    "stub": ("Code", "Tracked"),
    "unknown": ("Confirm", "Tracked"),
    "absent": ("Tracked", "Code"),
    "deprecated": ("Evidence", "Tracked"),
    "superseded": ("Code", "Tracked"),
    "removed": ("Evidence", "Tests"),
}


@pytest.mark.parametrize("base", STATUSES)
def test_u3_s1_kill_pair_per_status(script, base):
    req, forb = _KILL_PAIRS[base]
    assert GRAMMAR_ORACLE[base][req] == REQ and GRAMMAR_ORACLE[base][forb] == FORBID
    clean = _required(base)
    status = _status_for(base)

    def errs(labels):
        return row_errors(script, md_doc(features=[_anchor(), _row("F-002", "T", status, labels)]))

    assert errs(clean) == []
    assert _labels_mentioned(req, "F-002", base, errs([x for x in clean if x != req]))
    assert _labels_mentioned(forb, "F-002", base, errs(clean + [forb]))


def _section_swap(md, fid, first, second):
    """Move the `second` bullet of `fid`'s section directly before `first`."""
    start = md.index(f"#### {fid} ")
    end = md.index("\n\n", start)
    lines = md[start:end].split("\n")
    a = next(i for i, x in enumerate(lines) if x.startswith(f"- **{first}:**"))
    b = next(i for i, x in enumerate(lines) if x.startswith(f"- **{second}:**"))
    moved = lines.pop(b)
    lines.insert(a, moved)
    return md[:start] + "\n".join(lines) + md[end:]


@pytest.mark.parametrize("later, earlier", [("Tests", "Confirm"), ("Code", "Evidence")])
def test_u3_f1_label_order_names_both_labels(script, later, earlier):
    base = md_doc(features=_two_features())
    assert row_errors(script, base) == []
    md = _section_swap(base, "F-002", later, earlier)
    assert md != base
    errors = row_errors(script, md)
    assert any("F-002" in e and later in e and earlier in e for e in errors), errors


@pytest.mark.parametrize(
    "status",
    [
        "done",
        "Accepted",
        "superseded",
        "superseded → F-999",
        "superseded → F-002",
        "superseded -> F-001",
        "accepted extra",
        "partial (x)",
    ],
)
def test_u3_f2_status_vocabulary_rejects(script, status):
    labels = _required("accepted")
    md = md_doc(features=[_anchor(), _row("F-002", "Under test", status, labels)])
    errors = row_errors(script, md)
    assert any("F-002" in e and repr(status) in e for e in errors), errors


def test_u3_f2_superseded_with_existing_target_is_clean(script):
    labels = _required("superseded")
    md = md_doc(features=[_anchor(), _row("F-002", "Under test", "superseded → F-001", labels)])
    assert row_errors(script, md) == []


def _three():
    return [
        _row("F-001", "One", "accepted", _required("accepted")),
        _row("F-002", "Two", "accepted", _required("accepted")),
        _row("F-003", "Foo", "accepted", _required("accepted")),
    ]


def test_u3_f3_three_row_base_is_clean(script):
    assert row_errors(script, md_doc(features=_three())) == []


def _f3_case(case):
    feats = _three()
    rows = summary_rows(feats)
    if case == "summary-without-section":
        return md_doc(features=feats[:2], summary=rows)
    if case == "section-without-summary":
        return md_doc(features=feats, summary=rows[:2])
    if case == "name-mismatch":
        return md_doc(features=feats[:2] + [dict(feats[2], name="Foo2")], summary=rows)
    if case == "status-mismatch":
        rows[2] = rows[2].replace("| accepted |", "| partial |")
        return md_doc(features=feats, summary=rows)
    if case == "empty-area":
        rows[2] = rows[2].replace("| EPUB processing |", "|  |")
        return md_doc(features=feats, summary=rows)
    raise AssertionError(case)


@pytest.mark.parametrize(
    "case, quoted",
    [
        ("summary-without-section", []),
        ("section-without-summary", []),
        ("name-mismatch", ["'Foo'", "'Foo2'"]),
        ("status-mismatch", ["'accepted'", "'partial'"]),
        ("empty-area", ["Area"]),
    ],
)
def test_u3_f3_summary_section_disagreement(script, case, quoted):
    md = _f3_case(case)
    assert md != md_doc(features=_three())
    errors = row_errors(script, md)
    assert any("F-003" in e and all(q in e for q in quoted) for e in errors), errors


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(nums=st.lists(st.integers(1, 12), min_size=1, max_size=8))
def test_u3_p4_id_sequence_law(script, nums):
    ids = [f"F-{n:03d}" for n in nums]
    feats = [_row(fid, f"Row {i}", "accepted", _required("accepted")) for i, fid in enumerate(ids)]
    errors = row_errors(script, md_doc(features=feats))
    if nums == list(range(1, len(nums) + 1)):
        assert errors == []
    else:
        offending = {ids[i] for i, n in enumerate(nums) if n != i + 1}
        assert any(fid in e for e in errors for fid in offending), (ids, errors)


@pytest.mark.parametrize("bad", ["F-1", "F-0001", "f-001", "F-00a"])
def test_u3_f4_malformed_id_quoted(script, bad):
    feats = [_anchor(), _row(bad, "Bad id", "accepted", _required("accepted"))]
    errors = row_errors(script, md_doc(features=feats))
    assert any(repr(bad) in e for e in errors), errors


def test_u3_b1_out_of_order_sections_are_fine(script):
    feats = _three()
    md = md_doc(features=[feats[2], feats[0], feats[1]], summary=summary_rows(feats))
    assert md.index("#### F-003") < md.index("#### F-001")
    assert row_errors(script, md) == []


# U3-P3: nine accepted rows; each injector touches its own row(s) only.
_P3_ROWS = 9


def _p3_md(defects):
    feats = [_row(f"F-{i:03d}", f"Row {i}", "accepted", _required("accepted")) for i in range(1, _P3_ROWS + 1)]
    rows = None
    if "absent+Code" in defects:
        feats[0] = _row("F-001", "Row 1", "absent", ["What", "Code", "Tracked"])
    if "accepted-no-Tests" in defects:
        feats[1] = _row("F-002", "Row 2", "accepted", [x for x in _required("accepted") if x != "Tests"])
    if "status-done" in defects:
        feats[3] = _row("F-004", "Row 4", "done", _required("accepted"))
    if "accepted+Tracked" in defects:
        feats[6] = _row("F-007", "Row 7", "accepted", _required("accepted") + ["Tracked"])
    if "duplicate-id" in defects:
        feats[7] = dict(feats[7], id="F-009")
    rows = summary_rows(feats)
    if "name-mismatch" in defects:
        rows[4] = rows[4].replace("| Row 5 |", "| Row five |")
    if "empty-area" in defects:
        rows[5] = rows[5].replace("| EPUB processing |", "|  |")
    md = md_doc(features=feats, summary=rows)
    if "confirm-before-tests" in defects:
        md = _section_swap(md, "F-003", "Tests", "Confirm")
    return md


_P3_CATALOG = [
    "absent+Code",
    "accepted-no-Tests",
    "confirm-before-tests",
    "status-done",
    "name-mismatch",
    "empty-area",
    "accepted+Tracked",
    "duplicate-id",
]


def test_u3_p3_catalog_each_defect_alone_is_reported(script):
    assert row_errors(script, _p3_md(set())) == []
    for d in _P3_CATALOG:
        assert row_errors(script, _p3_md({d})) != [], d


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(defects=st.sets(st.sampled_from(_P3_CATALOG), min_size=2))
def test_u3_p3_independent_defects_add_up(script, defects):
    combined = set(row_errors(script, _p3_md(defects)))
    union = set()
    for d in defects:
        union |= set(row_errors(script, _p3_md({d})))
    assert union <= combined, sorted(union - combined)
    assert len(combined) >= len(defects)


def test_u3_validate_aggregates_parse_and_row_errors(script):
    # Wiring: the pipeline reports a parse-stage defect (unknown label) and a
    # row-grammar defect (missing Tests) in one call, and returns the parsed data.
    md = _with_f2(Tests=None)
    md = _f2_section_edit(md, _WHAT_LINE, _WHAT_LINE + "\n- **Limit:** x")
    data, errors = script.validate(md)
    assert any("F-002" in e and "Limit" in e for e in errors), errors
    assert any("F-002" in e and "Tests" in e and "accepted" in e for e in errors), errors
    assert [f["id"] for f in data["features"]] == ["F-001", "F-002"]


def test_u3_validate_clean_md_equals_parse_ledger(script):
    md = md_doc(features=_two_features())
    assert script.validate(md) == (script.parse_ledger(md)[0], [])


# ---------------------------------------------------------------------------
# WI-4: repo-reference validation
# ---------------------------------------------------------------------------

REPO_SNAPSHOT = "# frozen routes\n#\n\nGET /\nGET /api/health\n"
REPO_PYPROJECT = (
    '[project]\nname = "x"\n\n'
    '[project.scripts]\nreader3 = "reader3_app.reader3:main"\n\n'
    '[build-system]\nrequires = ["setuptools"]\n'
)
BLOCK_OPEN = '<script type="application/json" id="ledger-data">'
REPO_HTML = (
    "<!doctype html>\n<html><head><title>Feature ledger</title></head><body>\n"
    f"{BLOCK_OPEN}{{}}</script>\n</body></html>\n"
)
REPO_FILES = ("src/a.py",)
REPO_DIRS = ("tests/unit",)


def feat(fid, routes=(), code=("`src/a.py`",), tests=("`tests/unit/`",), status="accepted"):
    """One accepted feature row; `code`/`tests` are raw backticked entries."""
    bullets = {"What": f"Does {fid}.", "Code": ", ".join(code), "Tests": ", ".join(tests)}
    if routes:
        bullets["Routes"] = ", ".join(f"`{r}`" for r in routes)
    bullets.update({"Confirm": "Run it.", "Evidence": "v1.0.0"})
    return {"id": fid, "name": f"Feature {fid}", "area": "Area", "status": status, "bullets": bullets}


def repo_md(*features):
    return md_doc(features=list(features))


def default_repo_md():
    return repo_md(feat("F-001", ["cli: reader3"]), feat("F-002", ["GET /", "GET /api/health"]))


def make_repo(tmp_path, **overrides):
    """A tiny repo under `tmp_path/repo`: md, 2-route snapshot, 1-script
    pyproject, the md's referenced paths, and an HTML file with an empty
    `ledger-data` block. An override of `None` omits that file."""
    opts = {
        "md": default_repo_md(),
        "snapshot": REPO_SNAPSHOT,
        "pyproject": REPO_PYPROJECT,
        "html": REPO_HTML,
        "files": REPO_FILES,
        "dirs": REPO_DIRS,
    }
    unknown = set(overrides) - set(opts)
    assert not unknown, f"unknown make_repo overrides: {unknown}"
    opts.update(overrides)
    root = tmp_path / "repo"
    root.mkdir()
    for rel, key in (
        ("docs/feature-ledger.md", "md"),
        ("docs/feature-ledger.html", "html"),
        ("tests/contract/routes.snapshot", "snapshot"),
        ("pyproject.toml", "pyproject"),
    ):
        if opts[key] is not None:
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(opts[key], encoding="utf-8")
    for rel in opts["files"]:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).touch()
    for rel in opts["dirs"]:
        (root / rel).mkdir(parents=True, exist_ok=True)
    return root


def refs(script, root):
    md = (root / "docs" / "feature-ledger.md").read_text(encoding="utf-8")
    data, errors = script.parse_ledger(md)
    assert errors == [], errors
    return script.validate_refs(data, root)


def test_u4_make_repo_default_is_clean(script, tmp_path):
    root = make_repo(tmp_path)
    assert refs(script, root) == []
    html = (root / "docs" / "feature-ledger.html").read_text(encoding="utf-8")
    assert f"{BLOCK_OPEN}{{}}</script>" in html


def named(errors, candidates):
    """Candidates that appear backticked in at least one error."""
    return {c for c in candidates if any(f"`{c}`" in e for e in errors)}


st_route = st.from_regex(r"(GET|POST|PUT|DELETE) /[a-z]{1,6}(/\{[a-z_]{1,6}\})?", fullmatch=True)
st_cli = st.from_regex(r"[a-z][a-z0-9-]{0,8}", fullmatch=True).map(lambda s: f"cli: {s}")


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=st.data())
def test_u4_p1_route_errors_equal_the_two_set_differences(script, tmp_path_factory, data):
    u_routes = data.draw(st.sets(st_route, min_size=1, max_size=6), label="U_routes")
    u_cli = data.draw(st.sets(st_cli, min_size=1, max_size=3), label="U_cli")
    universe = u_routes | u_cli
    subset = data.draw(st.sets(st.sampled_from(sorted(universe))), label="claimed")
    extra = data.draw(
        st.sets(st.one_of(st_route, st_cli).filter(lambda r: r not in universe), max_size=2),
        label="unknown",
    )
    claims = sorted(subset | extra)
    n_rows = data.draw(st.integers(1, 3), label="rows")
    owner = {c: data.draw(st.integers(0, n_rows - 1)) for c in claims}
    features = [
        feat(f"F-{i + 1:03d}", [c for c in claims if owner[c] == i]) for i in range(n_rows)
    ]
    snapshot = "# routes\n" + "".join(f"{r}\n" for r in sorted(u_routes))
    pyproject = "[project.scripts]\n" + "".join(
        f'{c[len("cli: "):]} = "m:main"\n' for c in sorted(u_cli)
    )
    root = make_repo(
        tmp_path_factory.mktemp("p1"),
        md=repo_md(*features),
        snapshot=snapshot,
        pyproject=pyproject,
    )
    errors = refs(script, root)
    expected = (set(claims) - universe) | (universe - set(claims))
    assert named(errors, universe | set(claims)) == expected, errors
    for c in set(claims) - universe:
        fid = f"F-{owner[c] + 1:03d}"
        assert any(fid in e and f"`{c}`" in e for e in errors), (c, errors)
    if not expected:
        assert errors == []


P2_ROUTES = ["GET /", "GET /api/health", "POST /api/notes/{book_id}"]


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=st.data())
def test_u4_p2_snapshot_noise_does_not_change_the_universe(script, tmp_path_factory, data):
    noise = st.lists(st.sampled_from(["", "# c", "#", "   "]), max_size=3)
    lines = []
    for r in P2_ROUTES:
        lines += data.draw(noise)
        lines.append(r + " " * data.draw(st.integers(0, 3)))
    lines += data.draw(noise)
    md = repo_md(feat("F-001", ["cli: reader3", *P2_ROUTES]))
    root = make_repo(tmp_path_factory.mktemp("p2"), md=md, snapshot="\n".join(lines) + "\n")
    assert refs(script, root) == []

    (root / "tests/contract/routes.snapshot").write_text(
        "\n".join(lines) + "\nDELETE /api/extra\n", encoding="utf-8"
    )
    errors = refs(script, root)
    assert len(errors) == 1, errors
    assert "`DELETE /api/extra`" in errors[0]


REAL_SHAPED_SNAPSHOT = (
    "\n".join(["# API v1 —— 冻结的路由清单。", "#"] + [f"# note {i}" for i in range(13)] + ["#"])
    + "\nGET /\nMOUNT /static\nGET /api/search/{book_id}\n"
)


def test_u4_s1_real_shaped_snapshot(script, tmp_path):
    routes = ["cli: reader3", "GET /", "MOUNT /static", "GET /api/search/{book_id}"]
    root = make_repo(tmp_path, md=repo_md(feat("F-001", routes)), snapshot=REAL_SHAPED_SNAPSHOT)
    assert refs(script, root) == []

    (root / "docs/feature-ledger.md").write_text(
        repo_md(feat("F-001", [r for r in routes if r != "MOUNT /static"])), encoding="utf-8"
    )
    errors = refs(script, root)
    assert len(errors) == 1, errors
    assert "MOUNT /static" in errors[0]


@pytest.mark.parametrize("claim", ["GET /api/search/{id}", "GET /api/search/{book_id} "])
def test_u4_f1_near_miss_route_is_not_accepted(script, tmp_path, claim):
    root = make_repo(
        tmp_path,
        md=repo_md(feat("F-001", ["cli: reader3"]), feat("F-002", [claim])),
        snapshot="GET /api/search/{book_id}\n",
    )
    errors = refs(script, root)
    assert any("F-002" in e and f"`{claim}`" in e for e in errors), errors
    assert any("`GET /api/search/{book_id}`" in e and "F-002" not in e for e in errors), errors


def test_u4_b1_same_route_claimed_by_two_rows_passes(script, tmp_path):
    md = repo_md(
        feat("F-001", ["cli: reader3", "GET /"]),
        feat("F-002", ["cli: reader3", "GET /api/health"]),
    )
    assert refs(script, make_repo(tmp_path, md=md)) == []


@pytest.mark.parametrize("snapshot", [None, "# only comments\n#\n\n   \n"], ids=["missing", "empty"])
def test_u4_f2_missing_or_empty_snapshot_is_fail_not_skip(script, tmp_path, snapshot):
    # No row claims an HTTP route, so nothing else could make the result non-empty.
    root = make_repo(tmp_path, md=repo_md(feat("F-001", ["cli: reader3"])), snapshot=snapshot)
    errors = refs(script, root)
    assert len(errors) == 1, errors
    assert "routes.snapshot" in errors[0]


PYPROJECT_DEFECTS = {
    "no-section": '[project]\nname = "x"\n',
    "zero-entries": '[project.scripts]\n\n[build-system]\nrequires = ["x"]\n',
    "unquoted-value": "[project.scripts]\nreader3 = main\n",
    "quoted-key": '[project.scripts]\n"reader3" = "x:main"\n',
    "trailing-comment": '[project.scripts]\nreader3 = "x"  # c\n',
    "inline-table": '[project]\nname = "x"\nscripts = {reader3 = "x"}\n',
    "no-pyproject": None,
}


@pytest.mark.parametrize("case", list(PYPROJECT_DEFECTS))
def test_u4_f3_pyproject_scanner_defects(script, tmp_path, case):
    root = make_repo(tmp_path, pyproject=PYPROJECT_DEFECTS[case])
    errors = refs(script, root)
    assert errors != []
    assert any("project.scripts" in e or "pyproject" in e for e in errors), errors


def test_u4_b2_scanner_stops_at_next_header_and_tolerates_comments(script, tmp_path):
    pyproject = (
        '[project.scripts]\n# c\n\nreader3 = "a:b"\nreader3-server = "c:d"\n'
        '[build-system]\nrequires = "x"\n'
    )
    md = repo_md(
        feat("F-001", ["cli: reader3", "cli: reader3-server"]),
        feat("F-002", ["GET /", "GET /api/health"]),
    )
    errors = refs(script, make_repo(tmp_path, md=md, pyproject=pyproject))
    assert errors == []
    assert not any("requires" in e for e in errors)


def test_u4_f4_unclaimed_cli_and_unknown_cli(script, tmp_path):
    pyproject = '[project.scripts]\nreader3 = "a:b"\nreader3-server = "c:d"\n'
    md = repo_md(
        feat("F-001", ["cli: reader3", "GET /", "GET /api/health"]),
        feat("F-002", ["cli: nope"]),
    )
    errors = refs(script, make_repo(tmp_path, md=md, pyproject=pyproject))
    assert any("`cli: reader3-server`" in e for e in errors), errors
    assert any("F-002" in e and "`cli: nope`" in e for e in errors), errors
    assert len(errors) == 2, errors


def test_u4_p3_missing_code_path_kill_pair(script, tmp_path):
    md = repo_md(
        feat("F-001", ["cli: reader3"], code=("`src/a.py`", "`src/missing.py`")),
        feat("F-002", ["GET /", "GET /api/health"]),
    )
    root = make_repo(tmp_path, md=md)
    errors = refs(script, root)
    assert len(errors) == 1, errors
    assert "F-001" in errors[0] and "`src/missing.py`" in errors[0]
    (root / "src/missing.py").touch()
    assert refs(script, root) == []


st_note = st.sampled_from(["", " (`test_x_*`)", " (a, b)", " (see `x`, `y`)"])
st_leaf = st.from_regex(r"[a-z0-9_-]{1,6}(\.py)?/?", fullmatch=True)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=st.data())
def test_u4_p3_path_existence_is_monotonic(script, tmp_path_factory, data):
    n = data.draw(st.integers(1, 5), label="n")
    paths = [f"p{i}/{data.draw(st_leaf)}" for i in range(n)]  # unique first segment
    entries = [f"`{p}`{data.draw(st_note)}" for p in paths]
    existing = data.draw(st.sets(st.sampled_from(paths)), label="existing")
    code, tests = entries[0::2], entries[1::2] or ["`tests/unit/`"]
    md = repo_md(
        feat("F-001", ["cli: reader3", "GET /", "GET /api/health"], code=code, tests=tests)
    )
    root = make_repo(tmp_path_factory.mktemp("p3"), md=md)

    def create(p):
        target = root / p
        if p.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()

    for p in existing:
        create(p)
    first = refs(script, root)
    missing = [p for p in paths if p not in existing]
    assert len(first) == len(missing), first
    for p in missing:
        assert any("F-001" in e and f"`{p}`" in e for e in first), (p, first)
    for p in existing:
        assert not any(f"`{p}`" in e for e in first), (p, first)

    for p in paths:
        create(p)
    second = refs(script, root)
    assert second == []
    assert len(second) <= len(first)


def test_u4_b3_note_stripped_and_directories_count(script, tmp_path):
    md = repo_md(
        feat("F-001", ["cli: reader3", "GET /", "GET /api/health"],
             code=("`frontend/`",), tests=("`tests/unit/` (`test_book_uuid_*`)",))
    )
    root = make_repo(tmp_path, md=md, dirs=("tests/unit", "frontend"))
    assert refs(script, root) == []

    (root / "tests" / "unit").rmdir()
    errors = refs(script, root)
    assert len(errors) == 1, errors
    assert "tests/unit/" in errors[0]
    assert "test_book_uuid" not in errors[0]


@pytest.mark.parametrize("kind", ["dotdot", "nested-dotdot", "absolute"])
def test_u4_f5_escaping_the_root_is_rejected_even_if_target_exists(script, tmp_path, kind):
    (tmp_path / "outside.py").touch()
    path = {
        "dotdot": "../outside.py",
        "nested-dotdot": "src/../../outside.py",
        "absolute": str(tmp_path / "outside.py"),
    }[kind]
    md = repo_md(feat("F-001", ["cli: reader3", "GET /", "GET /api/health"], code=(f"`{path}`",)))
    errors = refs(script, make_repo(tmp_path, md=md))
    assert len(errors) == 1, errors
    assert "F-001" in errors[0] and path in errors[0]


def test_u4_f5_dotdot_staying_inside_root_is_allowed(script, tmp_path):
    md = repo_md(
        feat("F-001", ["cli: reader3", "GET /", "GET /api/health"], code=("`src/../README.md`",))
    )
    root = make_repo(tmp_path, md=md, files=("src/a.py", "README.md"))
    assert refs(script, root) == []


def test_u4_validate_with_repo_root_aggregates_parse_row_and_ref_errors(script, tmp_path):
    md = _with_f2(Tests=None)  # row-grammar defect: accepted without Tests
    md = _f2_section_edit(md, _WHAT_LINE, _WHAT_LINE + "\n- **Limit:** x")  # parse defect
    root = make_repo(tmp_path, md=md)  # F-001's Code path is absent from this repo
    data, errors = script.validate(md, repo_root=root)
    assert any("F-002" in e and "Limit" in e for e in errors), errors
    assert any("F-002" in e and "Tests" in e and "accepted" in e for e in errors), errors
    assert any("`src/reader3_app/reader3.py`" in e for e in errors), errors
    assert any("`GET /api/health`" in e for e in errors), errors
    assert [f["id"] for f in data["features"]] == ["F-001", "F-002"]


def test_u4_validate_with_clean_repo_equals_parse_ledger(script, tmp_path):
    root = make_repo(tmp_path)
    md = default_repo_md()
    assert script.validate(md, repo_root=root) == (script.parse_ledger(md)[0], [])


# ---------------------------------------------------------------------------
# WI-5: Audit log parse + validate; Synced <-> audit cross-check
# ---------------------------------------------------------------------------

AUDIT_KEYS = ["date", "title", "commit", "scope", "found", "not_audited"]

# Copied verbatim from docs/feature-ledger.md (the two 2026-09-27 entries).
REAL_AUDIT_LINES = [
    '### 2026-09-27 — Format extension + surface pass (`8e1cf48`)',
    '- **Scope:** every row F-001..F-030 re-read against code, templates and `tests/contract/routes.snapshot` to fill the new `Routes` / `Confirm` / `Tracked` bullets; the `Limits` of every row plus the 009 debt table (#11, #21, #52, #53, #57, #58) and `spec-frontend-design.md` §D1 checked for surfaces with no behaviour. Added the `stub` / `absent` / `unknown` statuses and rows F-031..F-041.',
    '- **Found:** F-017 claimed all-books / one-book / collection scope, but only single-book chat exists (`chat.ts` header; the other two buttons are disabled "Coming soon") — `What` corrected and F-039 split out; its status stays `accepted` for the single-book scope. #57, #52 and #53 were expected to be `absent` but each has a visible UI control (Add books, 重建全部索引, 导出书库 JSON), so they are `stub`. Two dead surfaces were not in any ledger row: the font-family picker (F-032) and 点评此书 (F-040). `reader3-server --help` starts the server (noted on F-027). F-010\'s `Code` pointed at `static/js/`, but the font-size wiring is an inline script in `reader.html`; the path was corrected.',
    "- **Not audited:** `Confirm` steps were derived from code and templates, not executed in a running app (only `uv run reader3 --help` was run). Lanes and e2e were not run. Whether the AI 偏好 toggles (显示消息时间, 自动推荐问题, 检索 片段数 / 上下文窗口) change behaviour was not checked. F-041 behaviour (CDN assets, offline) and epub.js / ChromaDB behaviour beyond what the rows' tests cover were not checked.",
    '',
    '### 2026-09-27 — Baseline seed (`8e1cf48`)',
    '- **Scope:** rows F-001..F-030 seeded retroactively from code + tests at `8e1cf48`, statuses taken from plan write-backs and the 009 debt table.',
    '- **Found:** —',
    '- **Not audited:** not re-run as an acceptance pass: no lane, e2e or manual check was executed for this seed; rows marked `baseline` carry no PR evidence.',
]


def _bullet_value(line):
    return line.split(":** ", 1)[1]


def test_u5_s1_real_md_entries_parse_exactly(script):
    md = md_doc(audit=[], trailer=REAL_AUDIT_LINES + [""] + CHECKLIST)
    data, errors = script.parse_ledger(md)
    assert errors == []
    expected = [
        {
            "date": "2026-09-27",
            "title": "Format extension + surface pass",
            "commit": "8e1cf48",
            "scope": _bullet_value(REAL_AUDIT_LINES[1]),
            "found": _bullet_value(REAL_AUDIT_LINES[2]),
            "not_audited": _bullet_value(REAL_AUDIT_LINES[3]),
        },
        {
            "date": "2026-09-27",
            "title": "Baseline seed",
            "commit": "8e1cf48",
            "scope": _bullet_value(REAL_AUDIT_LINES[6]),
            "found": "—",
            "not_audited": _bullet_value(REAL_AUDIT_LINES[8]),
        },
    ]
    assert data["audit"] == expected
    assert [list(a) for a in data["audit"]] == [AUDIT_KEYS, AUDIT_KEYS]
    assert data["audit"][0]["title"] == "Format extension + surface pass"
    assert data["audit"][0]["commit"] == "8e1cf48"
    assert data["audit"][1]["found"] == "—"
    assert "Gating" not in str(data["audit"])


_TRAILING_SHA = re.compile(r" \(`[0-9a-f]{7,40}`\)$")
st_title = st_line.filter(lambda s: not _TRAILING_SHA.search(s))
st_audit_entry = st.fixed_dictionaries(
    {
        "date": st.dates(min_value=date(2000, 1, 1), max_value=date(2099, 12, 31)),
        "title": st_title,
        "commit": st.text("0123456789abcdef", min_size=7, max_size=40),
        "scope": st_line,
        "found": st.one_of(st.just("—"), st_line),
        "not_audited": st_line,
    }
)


@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(entries=st.lists(st_audit_entry, min_size=1, max_size=4))
def test_u5_p1_audit_entries_round_trip(script, entries):
    entries = sorted(entries, key=lambda e: e["date"], reverse=True)
    audit = [dict(e, date=e["date"].isoformat()) for e in entries]
    newest = audit[0]["date"]
    data, errors = script.parse_ledger(md_doc(audit=audit, synced=(newest, "8e1cf48")))
    assert errors == []
    assert data["audit"] == audit
    assert all(list(a) == AUDIT_KEYS for a in data["audit"])


def _dated_audit(dates):
    return [dict(DEFAULT_AUDIT, date=d, title=f"Pass {i}") for i, d in enumerate(dates)]


@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(dates=st.lists(st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)), min_size=1, max_size=6))
@example(dates=[date(2026, 9, 27), date(2026, 9, 27)])
@example(dates=[date(2026, 9, 26), date(2026, 9, 27)])
def test_u5_p2_date_order_law(script, dates):
    iso = [d.isoformat() for d in dates]
    md = md_doc(audit=_dated_audit(iso), synced=(max(iso), "8e1cf48"))
    _, errors = script.validate(md)
    if all(a >= b for a, b in zip(dates, dates[1:])):
        assert errors == []
    else:
        assert errors, "ascending audit dates must be an error"
        for a, b in zip(iso, iso[1:]):
            if a < b:
                assert any(a in e and b in e for e in errors), (a, b, errors)


def test_u5_p2_kill_pair_equal_dates_clean_ascending_errors(script):
    same = md_doc(audit=_dated_audit(["2026-09-27", "2026-09-27"]))
    assert script.validate(same)[1] == []
    up = md_doc(audit=_dated_audit(["2026-09-26", "2026-09-27"]))
    errors = script.validate(up)[1]
    assert any("2026-09-26" in e and "2026-09-27" in e for e in errors), errors


@settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    synced=st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)),
    audited=st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31)),
)
@example(synced=date(2026, 9, 26), audited=date(2026, 9, 27))
@example(synced=date(2026, 9, 27), audited=date(2026, 9, 27))
def test_u5_p3_synced_not_before_newest_audit(script, synced, audited):
    s, a = synced.isoformat(), audited.isoformat()
    md = md_doc(audit=[dict(DEFAULT_AUDIT, date=a)], synced=(s, "8e1cf48"))
    _, errors = script.validate(md)
    if synced < audited:
        assert any("Synced" in e and s in e and a in e for e in errors), errors
    else:
        assert errors == []


def test_u5_p3_cross_check_uses_newest_entry(script):
    # Only the newest (first) entry's date matters, not the last one's.
    md = md_doc(audit=_dated_audit(["2026-09-27", "2026-09-01"]), synced=("2026-09-20", "8e1cf48"))
    errors = script.validate(md)[1]
    assert any("Synced" in e and "2026-09-20" in e and "2026-09-27" in e for e in errors), errors


def test_u5_b1_audit_intro_prose_is_ignored(script):
    intro = "Entries are newest first; see checklist 7."
    data, errors = script.parse_ledger(md_doc(audit_intro=intro))
    assert errors == []
    assert len(data["audit"]) == 1
    assert not any("Entries are newest first" in v for v in data["audit"][0].values())


_GOOD_HEADING = "### 2026-09-27 — Baseline seed (`8e1cf48`)"


@pytest.mark.parametrize(
    "heading",
    [
        "### 2026-09-27 - Baseline seed (`8e1cf48`)",
        "### 2026-09-27 — Baseline seed (8e1cf48)",
        "### 2026-02-30 — Baseline seed (`8e1cf48`)",
        "### 2026-09-27 — Baseline seed (`XYZ`)",
    ],
)
def test_u5_f1_heading_defect_quotes_the_heading(script, heading):
    md = md_doc()
    assert _GOOD_HEADING in md
    _, errors = script.parse_ledger(md.replace(_GOOD_HEADING, heading))
    text = heading[len("### "):]
    assert any(text in e for e in errors), errors


def test_u5_f1_title_with_paren_and_plus_parses(script):
    audit = [dict(DEFAULT_AUDIT, title="Format extension + surface pass (round 2)")]
    data, errors = script.parse_ledger(md_doc(audit=audit))
    assert errors == []
    assert data["audit"][0]["title"] == "Format extension + surface pass (round 2)"
    assert data["audit"][0]["commit"] == "8e1cf48"


_SCOPE = "- **Scope:** rows seeded"
_FOUND = "- **Found:** —"
_NOT = "- **Not audited:** no lane run"


def _audit_bullet_defects():
    return {
        "not-audited-missing": (_NOT + "\n", ""),
        "found-before-scope": (_SCOPE + "\n" + _FOUND, _FOUND + "\n" + _SCOPE),
        "extra-notes": (_NOT, _NOT + "\n- **Notes:** x"),
        "scope-duplicated": (_SCOPE, _SCOPE + "\n" + _SCOPE),
        "found-empty": (_FOUND, "- **Found:**"),
        "prose-line": (_FOUND, _FOUND + "\nSome prose inside the entry."),
    }


@pytest.mark.parametrize("case", list(_audit_bullet_defects()))
def test_u5_f2_bullet_defect_names_the_entry(script, case):
    old, new = _audit_bullet_defects()[case]
    md = md_doc()
    assert old in md
    _, errors = script.parse_ledger(md.replace(old, new))
    assert any("2026-09-27" in e and "Baseline seed" in e for e in errors), (case, errors)


def test_u5_f2_default_entry_is_clean(script):
    # Kill-pair anchor for U5-F2.
    assert script.parse_ledger(md_doc())[1] == []


def test_u5_f3_empty_audit_section(script):
    md = md_doc(audit=[], trailer=CHECKLIST)
    assert "## Audit log\n\n## Update checklist" in md
    data, errors = script.parse_ledger(md)
    assert data["audit"] == []
    assert any("Audit log" in e for e in errors), errors


def test_u1_b2_ghost_heading_under_audit_log_is_an_audit_grammar_error(script):
    # U1-B2 revisited by WI-5: the stray `####` block after the valid entry is
    # reported by audit grammar, naming the entry it sits in.
    ghost = ["#### F-099 Ghost — accepted", "- **What:** x", ""]
    data, errors = script.parse_ledger(md_doc(trailer=ghost + CHECKLIST))
    assert any("F-099 Ghost" in e and "2026-09-27" in e and "Baseline seed" in e for e in errors), errors
    assert len(data["audit"]) == 1


# ---------------------------------------------------------------------------
# WI-6: render_block / splice / diff_summary
# ---------------------------------------------------------------------------

OPEN_TAG = '<script type="application/json" id="ledger-data">'
CLOSE_TAG = "</script>"


def extract_block(html):
    """Interior of the one ledger-data block: after the full opening tag, up to
    the first `</script>` after it. Written here, never imported from the script."""
    start = html.index(OPEN_TAG) + len(OPEN_TAG)
    return html[start : html.index(CLOSE_TAG, start)]


def splice_error(script, html, block):
    """The error message of a failed splice, whichever channel it uses
    (an error list or a raised exception). A success is a test failure."""
    try:
        out, errors = script.splice(html, block)
    except Exception as exc:  # noqa: BLE001 - either channel is acceptable
        return str(exc)
    assert errors, f"splice reported success on invalid HTML: {out!r}"
    return "\n".join(errors)


_HOSTILE = [
    "</script>",
    "</SCRIPT >",
    "<!--",
    "<!-- x -->",
    "</",
    "\\</script>",
    '"',
    "→",
    "é",
    "\u2028",
]
st_hostile = st.builds(
    lambda a, b, c: a + b + c,
    st.text(max_size=8),
    st.one_of(st.text(max_size=8), st.sampled_from(_HOSTILE)),
    st.text(max_size=8),
)
st_hostile_feature = st.fixed_dictionaries(
    {
        "id": st.just("F-001"),
        "name": st_hostile,
        "area": st_hostile,
        "status": st.just("accepted"),
        "what": st_hostile,
        "routes": st.lists(st_hostile, max_size=2),
        "code": st.lists(st_hostile, max_size=2),
        "tests": st.lists(st_hostile, max_size=2),
        "adr": st.lists(st_adr, max_size=1),
        "confirm": st_hostile,
        "tracked": st_hostile,
        "evidence": st_hostile,
        "limits": st_hostile,
    }
)
st_hostile_audit = st.fixed_dictionaries(
    {
        "date": st.just("2026-09-27"),
        "title": st_hostile,
        "commit": st.just("8e1cf48"),
        "scope": st_hostile,
        "found": st_hostile,
        "not_audited": st_hostile,
    }
)


def ledger_data(features, audit):
    return {
        "synced_from": "docs/feature-ledger.md",
        "synced_at": "2026-09-27",
        "commit": "8e1cf48",
        "statuses": list(STATUSES),
        "features": features,
        "audit": audit,
    }


AUDIT_ENTRY = {
    "date": "2026-09-27",
    "title": "Baseline",
    "commit": "8e1cf48",
    "scope": "s",
    "found": "f",
    "not_audited": "—",
}


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    features=st.lists(st_hostile_feature, max_size=3),
    audit=st.lists(st_hostile_audit, max_size=2),
)
@example(
    features=[
        {
            "id": "F-001",
            "name": "n",
            "area": "a",
            "status": "accepted",
            "what": "w",
            "routes": [],
            "code": [],
            "tests": [],
            "adr": [],
            "confirm": "</script><script>alert(1)</script>",
            "tracked": "",
            "evidence": "e",
            "limits": "",
        }
    ],
    audit=[dict(AUDIT_ENTRY, found="</SCRIPT> and <!-- x -->")],
)
def test_u6_p1_hostile_round_trip_and_escape_invariant(script, features, audit):
    data = ledger_data(features, audit)
    block = script.render_block(data)
    assert json.loads(block) == data
    assert re.search(r"(?i)</script|<!--", block) is None, block


def test_u6_p1_script_breakout_in_confirm(script):
    evil = "</script><script>alert(1)</script>"
    f = dict(_S1_F1, confirm=evil)
    block = script.render_block(ledger_data([f], [AUDIT_ENTRY]))
    assert "</script" not in block.lower()
    assert json.loads(block)["features"][0]["confirm"] == evil


_S1_F1 = {
    "id": "F-001",
    "name": "A",
    "area": "X",
    "status": "accepted",
    "what": "w",
    "routes": ["GET /"],
    "code": ["a.py"],
    "tests": ["t.py"],
    "adr": [],
    "confirm": "c",
    "tracked": "",
    "evidence": "e",
    "limits": "",
}
_S1_F2 = {
    "id": "F-002",
    "name": "B",
    "area": "Y",
    "status": "absent",
    "what": "v",
    "routes": [],
    "code": [],
    "tests": [],
    "adr": ["ADR-0001"],
    "confirm": "",
    "tracked": "T",
    "evidence": "",
    "limits": "l",
}


def test_u6_s1_exact_layout_literal(script):
    expected = (
        '{"synced_from": "docs/feature-ledger.md", "synced_at": "2026-09-27", '
        '"commit": "8e1cf48", "statuses": ["accepted", "partial", "stub", "absent", '
        '"unknown", "deprecated", "superseded", "removed"], "features": [\n'
        '  {"id": "F-001", "name": "A", "area": "X", "status": "accepted", "what": "w", '
        '"routes": ["GET /"], "code": ["a.py"], "tests": ["t.py"], "adr": [], '
        '"confirm": "c", "tracked": "", "evidence": "e", "limits": ""},\n'
        '  {"id": "F-002", "name": "B", "area": "Y", "status": "absent", "what": "v", '
        '"routes": [], "code": [], "tests": [], "adr": ["ADR-0001"], '
        '"confirm": "", "tracked": "T", "evidence": "", "limits": "l"}\n'
        '], "audit": [\n'
        '  {"date": "2026-09-27", "title": "Baseline", "commit": "8e1cf48", '
        '"scope": "s", "found": "f", "not_audited": "—"}\n'
        "]}"
    )
    assert script.render_block(ledger_data([_S1_F1, _S1_F2], [AUDIT_ENTRY])) == expected


def test_u6_b1_non_ascii_emitted_literally(script):
    what = "café → 「点评此书」"
    block = script.render_block(ledger_data([dict(_S1_F1, what=what)], [AUDIT_ENTRY]))
    assert f'"what": "{what}"' in block
    assert "\\u" not in block


def test_u6_b2_comment_open_escape_is_valid_json(script):
    block = script.render_block(ledger_data([_S1_F1], [dict(AUDIT_ENTRY, found="a <!-- b")]))
    assert json.loads(block)["audit"][0]["found"] == "a <!-- b"
    assert "\\u003c!--" in block
    assert "<!--" not in block


def test_u6_b3_uppercase_close_tag_in_audit_escaped(script):
    block = script.render_block(ledger_data([_S1_F1], [dict(AUDIT_ENTRY, found="x </SCRIPT> y")]))
    assert "</SCRIPT" not in block
    assert "<\\/SCRIPT>" in block
    assert json.loads(block)["audit"][0]["found"] == "x </SCRIPT> y"


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(features=st_features())
def test_u6_d1_deterministic_without_env_or_cwd(script, features, tmp_path_factory):
    data = ledger_data(features, [AUDIT_ENTRY])
    first = script.render_block(data)
    elsewhere = tmp_path_factory.mktemp("cwd")
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(elsewhere)
        mp.setenv("TZ", "Pacific/Kiritimati")
        mp.setenv("SOURCE_DATE_EPOCH", "0")
        second = script.render_block(copy.deepcopy(data))
    assert first == second


def _html(prefix, interior, suffix):
    return prefix + OPEN_TAG + interior + CLOSE_TAG + suffix


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    prefix=st.text().filter(lambda s: OPEN_TAG not in s),
    suffix=st.one_of(
        st.text(),
        st.builds(lambda a, b: a + "<script>var x = 1;</script>" + b, st.text(), st.text()),
    ).filter(lambda s: OPEN_TAG not in s),
    old=st.text().filter(lambda s: "</script" not in s.lower()),
    features=st_features(max_size=3),
)
def test_u6_p2_prefix_suffix_conserved_and_idempotent(script, prefix, suffix, old, features):
    data = ledger_data(features, [AUDIT_ENTRY])
    block = script.render_block(data)
    out, errors = script.splice(_html(prefix, old, suffix), block)
    assert errors == []
    assert out.startswith(prefix + OPEN_TAG)
    assert out.endswith(CLOSE_TAG + suffix)
    assert script.splice(out, block) == (out, [])
    assert json.loads(extract_block(out)) == data


def test_u6_p2_interior_is_block_wrapped_in_single_newlines(script):
    # Surrounding-newline convention: the tag, "\n", the block, "\n", "</script>".
    out, errors = script.splice(_html("<p>", "old", "</p>"), "BLOCK")
    assert errors == []
    assert out == "<p>" + OPEN_TAG + "\nBLOCK\n" + CLOSE_TAG + "</p>"


@pytest.mark.parametrize(
    "html",
    [
        pytest.param("<html><body>no block</body></html>", id="zero"),
        pytest.param(_html("", "\n{}\n", "") + _html("", "\n{}\n", ""), id="two"),
        pytest.param("<head>" + OPEN_TAG + "\n{}\n<style></style>", id="unterminated"),
        pytest.param(
            '<script id="ledger-data" type="application/json">\n{}\n</script>',
            id="attribute-order",
        ),
    ],
)
def test_u6_f1_block_count_errors_name_ledger_data(script, html):
    assert "ledger-data" in splice_error(script, html, "{}")


def test_u6_b4_ledger_data_substring_elsewhere_is_not_a_block(script):
    comment = "<!-- generated; do not hand-edit the ledger-data block -->\n"
    footer = "\n<footer><code>#ledger-data</code></footer>\n"
    html = "<head>\n" + comment + OPEN_TAG + "\nOLD\n" + CLOSE_TAG + footer
    out, errors = script.splice(html, "NEW")
    assert errors == []
    assert out == "<head>\n" + comment + OPEN_TAG + "\nNEW\n" + CLOSE_TAG + footer


def test_u6_b5_real_html_splice_with_own_block_is_identity(script):
    html = (REPO_ROOT / "docs" / "feature-ledger.html").read_text(encoding="utf-8")
    own = extract_block(html)
    assert own.startswith("\n") and own.endswith("\n")
    assert script.splice(html, own[1:-1]) == (html, [])


def _lines(n, changed=None, value="a"):
    return "\n".join(value if i == changed else f"row {i}" for i in range(1, n + 1)) + "\n"


def test_u6_s2_diff_names_changed_line_and_is_bounded(script):
    out = script.diff_summary(_lines(200, 150, "a"), _lines(200, 150, "b"))
    lines = out.splitlines()
    assert any(line.startswith("-") and line.endswith("a") and not line.startswith("---") for line in lines), out
    assert any(line.startswith("+") and line.endswith("b") and not line.startswith("+++") for line in lines), out
    assert 0 < len(lines) <= 40


def test_u6_s2_diff_bounded_when_everything_differs(script):
    old = "".join(f"old {i}\n" for i in range(200))
    new = "".join(f"new {i}\n" for i in range(200))
    out = script.diff_summary(old, new)
    assert out != ""
    assert len(out.splitlines()) <= 40


def test_u6_s2_identical_inputs_give_empty_diff(script):
    assert script.diff_summary(_lines(200), _lines(200)) == ""


# ---------------------------------------------------------------------------
# WI-4 fix (found in WI-7): a relative repo root
# ---------------------------------------------------------------------------


def test_u4_relative_root_gives_same_errors_as_absolute(script, tmp_path, monkeypatch):
    # `os.path.commonpath([".", "src/a.py"])` is "", so a relative root used to
    # report every path as "resolves outside the repo root".
    md = repo_md(
        feat("F-001", ["cli: reader3"], code=("`src/a.py`", "`src/gone.py`")),
        feat("F-002", ["GET /", "GET /api/health"], code=("`../outside.py`",)),
    )
    root = make_repo(tmp_path, md=md)
    absolute = script.validate(md, repo_root=root)
    monkeypatch.chdir(root)
    relative = script.validate(md, repo_root=Path("."))
    assert relative == absolute
    errors = absolute[1]
    assert any("src/gone.py" in e and "does not exist" in e for e in errors), errors
    assert any("../outside.py" in e and "outside" in e for e in errors), errors
    assert not any("src/a.py" in e for e in errors), errors


def test_u4_relative_root_clean_repo_is_clean(script, tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    md = (root / "docs" / "feature-ledger.md").read_text(encoding="utf-8")
    monkeypatch.chdir(root.parent)
    assert script.validate(md, repo_root=Path("repo"))[1] == []


# ---------------------------------------------------------------------------
# WI-7: CLI (build + --check)
# ---------------------------------------------------------------------------

FIX_COMMAND = "python3 scripts/build_feature_ledger.py"


def html_path(root):
    return root / "docs" / "feature-ledger.html"


def md_path(root):
    return root / "docs" / "feature-ledger.md"


def built_repo(script, tmp_path, **overrides):
    root = make_repo(tmp_path, **overrides)
    assert script.run(root, check=False) == 0
    return root


def snapshot_state(path):
    return path.read_bytes(), path.stat().st_mtime_ns


def _edit_md(root, old, new):
    text = md_path(root).read_text(encoding="utf-8")
    assert old in text, old
    md_path(root).write_text(text.replace(old, new, 1), encoding="utf-8")


def _edit_block(root, old, new):
    text = html_path(root).read_text(encoding="utf-8")
    assert old in text, old
    html_path(root).write_text(text.replace(old, new, 1), encoding="utf-8")


def test_u7_s1_build_rebuild_idempotent_then_check_clean(script, tmp_path):
    root = make_repo(tmp_path)
    before = html_path(root).read_bytes()
    assert script.run(root, check=False) == 0
    first = html_path(root).read_bytes()
    assert first != before
    md = md_path(root).read_text(encoding="utf-8")
    expected, errors = script.parse_ledger(md)
    assert errors == []
    text = first.decode("utf-8")
    assert "\r" not in text
    assert json.loads(extract_block(text)) == expected
    assert [f["id"] for f in json.loads(extract_block(text))["features"]] == ["F-001", "F-002"]
    # bytes outside the block are the template's
    assert text.startswith(REPO_HTML[: REPO_HTML.index(BLOCK_OPEN)])
    assert text.endswith("</script>\n</body></html>\n")
    assert script.run(root, check=False) == 0
    assert html_path(root).read_bytes() == first
    assert script.run(root, check=True) == 0
    assert html_path(root).read_bytes() == first


def test_u7_p1_check_never_writes_and_failed_build_never_writes(script, tmp_path):
    root = built_repo(script, tmp_path)
    html = html_path(root)

    state = snapshot_state(html)
    assert script.run(root, check=True) == 0
    assert snapshot_state(html) == state

    _edit_block(root, '"name": "Feature F-001"', '"name": "Hand edited"')
    state = snapshot_state(html)
    assert script.run(root, check=True) == 1
    assert snapshot_state(html) == state

    _edit_block(root, '"name": "Hand edited"', '"name": "Feature F-001"')
    _edit_md(root, "Does F-001.", "Does F-001 differently.")
    state = snapshot_state(html)
    assert script.run(root, check=True) == 1
    assert snapshot_state(html) == state

    (root / "src" / "a.py").unlink()
    state = snapshot_state(html)
    assert script.run(root, check=True) == 1
    assert snapshot_state(html) == state
    assert script.run(root, check=False) == 1
    assert snapshot_state(html) == state


def test_u7_f1_hand_edited_block_is_drift_with_fix_command(script, tmp_path, capsys):
    root = built_repo(script, tmp_path)
    capsys.readouterr()
    _edit_block(root, '"name": "Feature F-001"', '"name": "Hand edited name"')
    before = html_path(root).read_bytes()
    assert script.run(root, check=True) == 1
    out = capsys.readouterr()
    text = out.out + out.err
    for needle in ("drift", "feature-ledger.md", "feature-ledger.html", FIX_COMMAND, "Hand edited name"):
        assert needle in text, (needle, text)
    assert html_path(root).read_bytes() == before


SYNCED_LINE = "**Synced:** 2026-09-27 at commit `8e1cf48`"


def _synced_line(root):
    lines = md_path(root).read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line.startswith("**Synced:**")]


STALE_MD_EDITS = {
    "a_feature_what": ("Does F-001.", "Does F-001 in a new way."),
    "b_synced_only": (SYNCED_LINE, "**Synced:** 2026-09-28 at commit `abcdef0`"),
    "c1_audit_found": ("- **Found:** —", "- **Found:** one row re-graded"),
    "c2_audit_new_entry": (
        "## Audit log\n\n",
        "## Audit log\n\n### 2026-09-27 — Second pass (`abcdef0`)\n"
        "- **Scope:** F-001\n- **Found:** nothing\n- **Not audited:** rest\n\n",
    ),
}


@pytest.mark.parametrize("case", sorted(STALE_MD_EDITS))
def test_u7_f2_stale_md_is_drift(script, tmp_path, capsys, case):
    root = built_repo(script, tmp_path)
    built_synced = _synced_line(root)
    capsys.readouterr()
    old, new = STALE_MD_EDITS[case]
    _edit_md(root, old, new)
    if case.startswith("c"):
        assert _synced_line(root) == built_synced
        _, errors = script.validate(md_path(root).read_text(encoding="utf-8"), root)
        assert errors == [], errors
    before = html_path(root).read_bytes()
    assert script.run(root, check=True) == 1
    out = capsys.readouterr()
    assert "drift" in out.out + out.err, out
    assert html_path(root).read_bytes() == before


def _f5_snapshot_route(root):
    snap = root / "tests" / "contract" / "routes.snapshot"
    snap.write_text(snap.read_text(encoding="utf-8") + "GET /extra\n", encoding="utf-8")


def _f5_delete_code(root):
    (root / "src" / "a.py").unlink()


def _f5_swap_tests_confirm(root):
    text = md_path(root).read_text(encoding="utf-8")
    head = "#### F-001 "
    start = text.index(head)
    end = text.index("####", start + len(head))
    section = text[start:end]
    swapped = section.replace(
        "- **Tests:** `tests/unit/`\n- **Confirm:** Run it.",
        "- **Confirm:** Run it.\n- **Tests:** `tests/unit/`",
    )
    assert swapped != section
    md_path(root).write_text(text[:start] + swapped + text[end:], encoding="utf-8")


def _f5_summary_status(root):
    _edit_md(root, "| F-001 | Feature F-001 | Area | accepted |", "| F-001 | Feature F-001 | Area | partial |")


F5_CASES = {
    "a_unclaimed_route": (_f5_snapshot_route, ("GET /extra",), False),
    "b_deleted_code": (_f5_delete_code, ("src/a.py",), False),
    "c_tests_confirm_swapped": (_f5_swap_tests_confirm, ("F-001", "Confirm", "Tests"), True),
    "d_summary_status_only": (_f5_summary_status, ("F-001", "accepted", "partial"), True),
}


@pytest.mark.parametrize("case", sorted(F5_CASES))
def test_u7_f5_check_runs_full_validation_when_block_in_sync(script, tmp_path, capsys, case):
    root = built_repo(script, tmp_path)
    capsys.readouterr()
    mutate, needles, same_render = F5_CASES[case]
    mutate(root)
    committed = html_path(root).read_text(encoding="utf-8")
    if same_render:
        data, _ = script.parse_ledger(md_path(root).read_text(encoding="utf-8"))
        spliced, errors = script.splice(committed, script.render_block(data))
        assert errors == []
        assert extract_block(spliced) == extract_block(committed)
    before = html_path(root).read_bytes()
    assert script.run(root, check=True) == 1
    err = capsys.readouterr().err
    for needle in needles:
        assert needle in err, (needle, err)
    assert html_path(root).read_bytes() == before


STYLED_HTML = (
    "<!doctype html>\n<html><head><title>Feature ledger</title>\n"
    "<style>\nbody { color: black; }\n</style>\n</head><body>\n"
    f"{BLOCK_OPEN}{{}}</script>\n</body></html>\n"
)

_outside_text = st.text(alphabet=st.characters(blacklist_categories=("Cs",))).filter(
    lambda t: "</script" not in t.lower() and BLOCK_OPEN not in t
)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(text=_outside_text, where=st.sampled_from(["style", "body"]))
@example(text="body { color: red; }", where="style")
@example(text="<p>ledger-data</p>", where="body")
def test_u7_p2_edits_outside_block_are_not_drift(script, tmp_path_factory, text, where):
    root = built_repo(script, tmp_path_factory.mktemp("p2"), html=STYLED_HTML)
    html = html_path(root).read_text(encoding="utf-8")
    anchor = "</style>" if where == "style" else "</body>"
    html_path(root).write_bytes(html.replace(anchor, text + anchor, 1).encode("utf-8"))
    assert script.run(root, check=True) == 0


def test_u7_f3_invalid_input_exit_1_bytes_unchanged_all_errors(script, tmp_path, capsys):
    absent = feat("F-002", ["GET /", "GET /api/health"], status="absent")
    root = make_repo(
        tmp_path,
        md=repo_md(feat("F-001", ["cli: reader3"]), absent),
        snapshot=REPO_SNAPSHOT + "GET /extra\n",
    )
    before = html_path(root).read_bytes()
    assert script.run(root, check=False) == 1
    err = capsys.readouterr().err
    assert "F-002" in err, err
    assert "GET /extra" in err, err
    assert html_path(root).read_bytes() == before


def _rm_md(root):
    md_path(root).unlink()


def _rm_html(root):
    html_path(root).unlink()


def _rm_docs(root):
    for p in (md_path(root), html_path(root)):
        p.unlink()
    (root / "docs").rmdir()


@pytest.mark.parametrize(
    "remove, names",
    [
        (_rm_md, ["feature-ledger.md"]),
        (_rm_html, ["feature-ledger.html"]),
        (_rm_docs, ["feature-ledger"]),
    ],
    ids=["md", "html", "docs"],
)
@pytest.mark.parametrize("check", [False, True], ids=["build", "check"])
def test_u7_f4_missing_input_files_exit_1_no_traceback(script, tmp_path, capsys, remove, names, check):
    root = make_repo(tmp_path)
    remove(root)
    argv = ["--root", str(root)] + (["--check"] if check else [])
    assert script.main(argv) == 1
    err = capsys.readouterr().err
    for name in names:
        assert name in err, err
    assert "Traceback" not in err
    if remove is not _rm_md:
        assert not html_path(root).exists()


def test_u7_main_build_then_check_via_argv(script, tmp_path, capsys):
    root = make_repo(tmp_path)
    assert script.main(["--root", str(root)]) == 0
    assert json.loads(extract_block(html_path(root).read_text(encoding="utf-8")))["commit"] == "8e1cf48"
    assert script.main(["--check", "--root", str(root)]) == 0


def test_u7_main_relative_root(script, tmp_path, monkeypatch, capsys):
    root = make_repo(tmp_path)
    monkeypatch.chdir(root)
    assert script.main(["--root", "."]) == 0, capsys.readouterr().err
    assert script.main(["--check", "--root", "."]) == 0, capsys.readouterr().err


def _cli(args, cwd):
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_u7_i1_subprocess_check_clean_then_drifted(script, tmp_path):
    root = built_repo(script, tmp_path)
    clean = _cli(["--check", "--root", str(root)], tmp_path)
    assert clean.returncode == 0, (clean.stdout, clean.stderr)
    assert "feature-ledger.html" in clean.stdout, (clean.stdout, clean.stderr)
    _edit_block(root, '"name": "Feature F-001"', '"name": "Hand edited"')
    drifted = _cli(["--check", "--root", str(root)], tmp_path)
    assert drifted.returncode == 1, (drifted.stdout, drifted.stderr)
    assert "drift" in drifted.stdout + drifted.stderr


def test_u7_i2_real_repo_check_clean_from_any_cwd(tmp_path):
    proc = _cli(["--check"], tmp_path)
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    # a script that does nothing also exits 0; the success report must be there
    assert "feature-ledger.html" in proc.stdout, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"


def test_u7_g1_script_imports_only_stdlib():
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"relative import at line {node.lineno}"
            roots.add((node.module or "").split(".")[0])
    offenders = sorted(r for r in roots if r not in sys.stdlib_module_names)
    assert roots, "no imports parsed"
    assert offenders == [], offenders


# ---------------------------------------------------------------------------
# WI-8: docs/feature-ledger.html template (data block cut out, test-side)
# ---------------------------------------------------------------------------

LEDGER_HTML = REPO_ROOT / "docs" / "feature-ledger.html"
DATA_OPEN_TAG = '<script type="application/json" id="ledger-data">'


def _template():
    html = LEDGER_HTML.read_text(encoding="utf-8")
    open_start = html.index(DATA_OPEN_TAG)
    close_start = html.index("</script>", open_start + len(DATA_OPEN_TAG))
    close_end = close_start + len("</script>")
    return html[:open_start] + html[close_end:]


def _light_block(template):
    m = re.search(r"(?m)^:root\s*\{(.*?)\}", template, re.S)
    assert m, "light :root block not found"
    return m.group(1)


def _dark_block(template):
    m = re.search(
        r"@media\s*\(prefers-color-scheme:\s*dark\)\s*\{\s*:root\s*\{(.*?)\}", template, re.S
    )
    assert m, "dark @media :root block not found"
    return m.group(1)


def _template_js(template):
    bodies = re.findall(r"<script>(.*?)</script>", template, re.S)
    assert bodies, "no non-JSON <script> in template"
    return "\n".join(bodies)


@pytest.mark.parametrize("status", STATUSES)
def test_u8_s1_status_has_class_rule_and_light_dark_vars(status):
    template = _template()
    light, dark = _light_block(template), _dark_block(template)
    assert re.search(rf"\.s-{status}\s*[{{,]", template), f".s-{status} rule missing"
    for name, block in (("light", light), ("dark", dark)):
        assert f"--{status}:" in block, f"--{status} missing in {name} block"
        assert f"--{status}-bg:" in block, f"--{status}-bg missing in {name} block"


def test_u8_s2_light_foreground_colours_pairwise_distinct():
    light = _light_block(_template())
    values = []
    for s in STATUSES:
        m = re.search(rf"--{s}:\s*([^;]+);", light)
        assert m, f"--{s} missing in light block"
        values.append(m.group(1).strip().lower())
    assert len(set(values)) == 8, dict(zip(STATUSES, values))


# U8-S3 (JS consumes routes / confirm / tracked / audit) was a source grep for
# identifiers and exact strings. Review C1 (2026-09-27): it pinned identifiers,
# not behaviour. The page JS is now executed in jsdom by
# `frontend/tests/ledger/feature-ledger-page.test.ts` (fe-unit lane), which
# expands rows and reads the rendered Routes / Confirm / Tracked and audit
# entries, so the grep is removed rather than loosened.


def test_u8_g1_no_html_sink_writes():
    # Kept as a cheap source backstop next to the jsdom test: that test proves
    # the fixture's hostile strings render as text; this one bans the sinks
    # for data the fixture does not happen to reach.
    template = _template()
    hit = re.search(r"\.(inner|outer)HTML\s*\+?=|insertAdjacentHTML|document\.write", template)
    assert hit is None, hit.group(0) if hit else None


def test_u8_g2_no_hardcoded_full_status_list():
    js = _template_js(_template())
    assert "DATA.statuses" in js
    needed = ('"accepted"', '"partial"', '"deprecated"', '"removed"')
    for lit in re.findall(r"\[[^\]]*\]", js):
        normalized = lit.replace("'", '"')
        assert not all(n in normalized for n in needed), f"hardcoded status list: {lit}"


# --- WI-9: CI wiring and docs -------------------------------------------------

LINT_YML = REPO_ROOT / ".github" / "workflows" / "lint.yml"
LEDGER_MD = REPO_ROOT / "docs" / "feature-ledger.md"
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
BUILD_CMD = "python3 scripts/build_feature_ledger.py"
HAND_MIRROR = re.compile(r"(?i)mirror\w*\b[^.\n]*ledger-data")


def _contracts_job():
    """Lines of the `contracts:` job, found by indentation, not by exact layout."""
    lines = LINT_YML.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if re.match(r"^\s*contracts:\s*$", ln))
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = next(
        (
            i for i in range(start + 1, len(lines))
            if lines[i].strip()
            and not lines[i].lstrip().startswith("#")
            and len(lines[i]) - len(lines[i].lstrip()) <= indent
        ),
        len(lines),
    )
    return lines[start:end]


def _steps(job):
    """The job's steps, each a list of lines; a step starts at a `- ` list item."""
    steps, current = [], None
    for ln in job:
        if re.match(r"^\s*- ", ln):
            current = [ln]
            steps.append(current)
        elif current is not None:
            current.append(ln)
    return steps


def test_u9_s1_lint_step_runs_check_after_router_size_with_always():
    # Review C1: step boundaries and the `if:` line are found by content, not
    # by exact indentation or by `if:` sitting between `name:` and `run:`.
    job = _contracts_job()
    steps = _steps(job)

    def runs(step, command):
        return any(re.search(r"\brun:\s*" + re.escape(command) + r"\s*$", ln) for ln in step)

    ledger = [i for i, st_ in enumerate(steps) if runs(st_, "python3 scripts/build_feature_ledger.py --check")]
    assert len(ledger) == 1, ledger
    router = [i for i, st_ in enumerate(steps) if runs(st_, "python3 scripts/check_router_size.py")]
    assert len(router) == 1, router
    assert ledger[0] > router[0]
    assert any(re.match(r"^\s*if:\s*always\(\)\s*$", ln) for ln in steps[ledger[0]])
    assert not any("uv sync" in ln for ln in job)


@pytest.mark.parametrize("path", [LEDGER_MD, CLAUDE_MD], ids=["ledger-md", "claude-md"])
def test_u9_s2_docs_name_build_and_check_without_hand_mirroring(path):
    text = path.read_text(encoding="utf-8")
    assert BUILD_CMD in text
    assert f"{BUILD_CMD} --check" in text
    hit = HAND_MIRROR.search(text)
    assert hit is None, hit.group(0) if hit else None


def _items(md, section):
    """Numbered list items of `## <section>`, each up to its next item or blank line."""
    start = md.index(f"\n## {section}")
    nxt = md.find("\n## ", start + 1)
    body = md[start : nxt if nxt >= 0 else len(md)]
    chunks = re.split(r"(?m)^\d+\. ", body)[1:]
    return [c.split("\n\n")[0] for c in chunks]


def _ledger_data_item(md, section):
    """The one item of `section` that talks about the generated block, by content
    (review C1: never by its `6. ` / `8. ` number)."""
    hits = [c for c in _items(md, section) if "feature-ledger.html" in c and "ledger-data" in c]
    assert len(hits) == 1, hits
    return hits[0]


def test_u9_s2_rule_names_build_command_and_no_mirror():
    md = LEDGER_MD.read_text(encoding="utf-8")
    rule = _ledger_data_item(md, "Rules")
    assert re.search(r"(?i)mirror", rule) is None, rule
    assert BUILD_CMD in rule
    assert "--check" in rule
    assert "is mirrored into that block" not in md


def test_u9_s2_checklist_names_build_and_no_mirror():
    md = LEDGER_MD.read_text(encoding="utf-8")
    item = _ledger_data_item(md, "Update checklist")
    assert re.search(r"(?i)mirror", item) is None, item
    assert BUILD_CMD in item
    assert "--check" in item


def _row_grammar_required_for():
    """Row grammar table: label (backticks stripped) -> its `Required for` cell."""
    md = LEDGER_MD.read_text(encoding="utf-8")
    start = md.index("## Row grammar")
    end = md.index("\n## ", start + 1)
    cells = {}
    for ln in md[start:end].splitlines():
        parts = [p.strip() for p in ln.split("|")]
        if len(parts) >= 4 and parts[1].strip("`") in LABEL_ORDER:
            cells[parts[1].strip("`")] = parts[2]
    return cells


def test_u9_s3_row_grammar_records_removed_ruling():
    # Review C1: only "Code and Tests exclude `removed`, Evidence does not".
    cells = _row_grammar_required_for()
    assert "removed" in cells["Code"], cells["Code"]
    assert "removed" in cells["Tests"], cells["Tests"]
    assert "removed" not in cells["Evidence"], cells["Evidence"]


# ---------------------------------------------------------------------------
# WI-10: review fixes (M1 area has one source, M2 nothing silently dropped,
# uncovered error paths, .gitattributes)
# ---------------------------------------------------------------------------


def _line_of(md, text):
    """1-based line number of the first line equal to `text`."""
    return md.split("\n").index(text) + 1


def _area_mismatch_md():
    feats = [_row("F-001", "One", "accepted", _required("accepted"))]
    feats.append(_row("F-002", "Two", "accepted", _required("accepted"), area="Reader"))
    rows = summary_rows(feats)
    rows[1] = rows[1].replace("| Reader |", "| Settings / UI |")
    return md_doc(features=feats, summary=rows), rows[1]


def test_u10_a1_summary_area_must_equal_enclosing_heading(script):
    md, bad_row = _area_mismatch_md()
    assert "### Reader\n\n#### F-002 Two" in md
    _, errors = script.validate(md)
    line = _line_of(md, bad_row)
    hits = [e for e in errors if "F-002" in e and "'Settings / UI'" in e and "'Reader'" in e]
    assert hits, errors
    assert any(f"line {line}" in e for e in hits), (line, hits)
    assert not any("F-001" in e for e in errors), errors


def test_u10_a1_kill_pair_matching_area_is_clean(script):
    feats = [
        _row("F-001", "One", "accepted", _required("accepted")),
        _row("F-002", "Two", "accepted", _required("accepted"), area="Reader"),
    ]
    data, errors = script.validate(md_doc(features=feats))
    assert errors == []
    assert [f["area"] for f in data["features"]] == ["EPUB processing", "Reader"]


def test_u10_a1_area_is_the_nearest_preceding_heading(script):
    # F-002 sits under `### Reader` even though its Summary row and F-001 say
    # EPUB processing: nearest preceding `###` wins, not the first one.
    feats = [
        _row("F-001", "One", "accepted", _required("accepted")),
        _row("F-002", "Two", "accepted", _required("accepted"), area="Reader"),
    ]
    rows = summary_rows(feats)
    rows[1] = rows[1].replace("| Reader |", "| EPUB processing |")
    _, errors = script.validate(md_doc(features=feats, summary=rows))
    assert any("F-002" in e and "'EPUB processing'" in e and "'Reader'" in e for e in errors), errors


def test_u10_a2_feature_section_without_area_heading_is_an_error(script):
    md = md_doc()
    assert "### EPUB processing\n\n" in md
    md = md.replace("### EPUB processing\n\n", "", 1)
    _, errors = script.validate(md)
    assert any("F-001" in e and "###" in e for e in errors), errors


def test_u10_a3_real_ledger_areas_are_its_feature_headings(script):
    # Review M1: the dashboard groups by `area`, so the set of areas must be
    # exactly the set of `###` headings under `## Features`, with nothing extra.
    md = LEDGER_MD.read_text(encoding="utf-8")
    features_body = md[md.index("\n## Features\n") : md.index("\n## Audit log\n")]
    headings = [ln[4:].strip() for ln in features_body.splitlines() if ln.startswith("### ")]
    data, errors = script.parse_ledger(md)
    assert errors == [], errors
    assert len(headings) == len(set(headings)), headings
    assert sorted({f["area"] for f in data["features"]}) == sorted(headings)


@pytest.mark.parametrize(
    "where",
    ["preamble", "under-area-heading"],
)
@pytest.mark.parametrize(
    "bullet",
    ["- **What:** stray value", "- a plain list item"],
    ids=["labelled", "plain"],
)
def test_u10_b1_bullet_outside_feature_section_is_an_error(script, where, bullet):
    base = md_doc()
    if where == "preamble":
        md = md_doc(preamble=bullet)
    else:
        md = base.replace("### EPUB processing\n\n", f"### EPUB processing\n\n{bullet}\n\n", 1)
    assert md != base
    _, errors = script.validate(md)
    line = _line_of(md, bullet)
    assert any(f"line {line}" in e and bullet in e for e in errors), (line, errors)


def test_u10_b1_prose_outside_feature_section_stays_allowed(script):
    # Kill pair for B1 and ruling 7: the same places holding prose are clean.
    md = md_doc(preamble="Paths are written out in full from the repo root.")
    md = md.replace("### EPUB processing\n\n", "### EPUB processing\n\nArea prose.\n\n", 1)
    assert script.validate(md)[1] == []


def test_u10_b2_feature_written_as_h3_is_an_error(script):
    base = md_doc(features=_two_features())
    head = "#### F-002 Semantic index CLI — accepted"
    assert head in base
    md = base.replace(head, head[1:], 1)
    _, errors = script.validate(md)
    line = _line_of(md, head[1:])
    assert any("F-002" in e and "####" in e and f"line {line}" in e for e in errors), errors


def test_u10_b2_area_heading_starting_with_f_word_is_fine(script):
    # Only `F-<digit>` marks a mis-levelled feature; an area may start with "F".
    feats = [_row("F-001", "One", "accepted", _required("accepted"), area="Frontend")]
    assert script.validate(md_doc(features=feats))[1] == []


def test_u10_c1_duplicate_section_reported_and_first_copy_kept(script):
    dup = ["## Summary", "", SUMMARY_HEADER, "|---|---|---|---|---|", "| F-009 | Ghost | X | accepted | e |", ""]
    md = md_doc(trailer=dup)
    data, errors = script.parse_ledger(md)
    assert any("`## Summary`" in e and "more than once" in e for e in errors), errors
    assert [f["id"] for f in data["features"]] == ["F-001"]
    summary = "\n".join(script.split_sections(md)["Summary"])
    assert ROW1 in summary and "F-009" not in summary


def _summary_table_md(lines):
    md = md_doc()
    table = SUMMARY_HEADER + "\n|---|---|---|---|---|\n" + ROW1 + "\n"
    assert table in md
    return md.replace(table, "".join(ln + "\n" for ln in lines), 1)


def test_u10_c2_summary_without_table(script):
    _, errors = script.parse_ledger(_summary_table_md([]))
    assert any("Summary" in e and "table" in e for e in errors), errors


def test_u10_c3_summary_header_only(script):
    md = _summary_table_md([SUMMARY_HEADER])
    _, errors = script.parse_ledger(md)
    line = _line_of(md, SUMMARY_HEADER)
    assert any("Summary" in e and f"line {line}" in e for e in errors), errors


@pytest.mark.parametrize(
    "sep",
    ["|---|---|---|---|", "|--|---|---|---|---|", "---|---|---|---|---"],
    ids=["four-cells", "two-dashes", "not-a-row"],
)
def test_u10_c4_malformed_separator(script, sep):
    md = _summary_table_md([SUMMARY_HEADER, sep, ROW1])
    _, errors = script.parse_ledger(md)
    line = _line_of(md, sep)
    assert any("Summary" in e and "separator" in e and f"line {line}" in e for e in errors), errors


def test_u10_c4_aligned_separator_is_fine(script):
    md = _summary_table_md([SUMMARY_HEADER, "|:---|---:|:---:|---|---|", ROW1])
    assert script.parse_ledger(md)[1] == []


def test_u10_c5_empty_backticked_entry_names_its_column(script):
    # "`a.py`, ` `": the second entry opens at column 9.
    _, errors = script.parse_ledger(_with_f2(Code="`a.py`, ` `"))
    assert any("F-002" in e and "Code" in e and "empty" in e and "column 9" in e for e in errors), errors


def test_u10_c6_empty_parenthetical_note(script):
    _, errors = script.parse_ledger(_with_f2(Tests="`a.py` ( )"))
    assert any("F-002" in e and "Tests" in e and "note" in e for e in errors), errors


def test_u10_c7_nested_paren_inside_note_parses(script):
    data, errors = script.parse_ledger(_with_f2(Tests="`a.py` (see f(x) and g(y)), `b.py`"))
    assert errors == []
    assert _f2(data)["tests"] == ["a.py (see f(x) and g(y))", "b.py"]


def test_u10_c8_non_utf8_ledger_check_exits_1_without_traceback(script, tmp_path, capsys):
    root = make_repo(tmp_path)
    md_path(root).write_bytes(b"# Feature Ledger\n\n\xff\xfe not utf-8 \x80\n")
    md_before, html_before = md_path(root).read_bytes(), html_path(root).read_bytes()
    assert script.run(root, check=True) == 1
    err = capsys.readouterr().err
    assert "cannot read" in err, err
    assert "feature-ledger.md" in err, err
    assert "Traceback" not in err
    assert md_path(root).read_bytes() == md_before
    assert html_path(root).read_bytes() == html_before


def test_u10_f1_gitattributes_pins_ledger_files_to_lf():
    # Review L3: a CRLF checkout would make `--check` report drift that is not there.
    path = REPO_ROOT / ".gitattributes"
    assert path.is_file(), f"{path} is missing"
    lines = path.read_text(encoding="utf-8").splitlines()
    for rel in ("docs/feature-ledger.md", "docs/feature-ledger.html"):
        rules = [ln.split() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]
        hits = [r for r in rules if r[0] == rel and "text" in r[1:] and "eol=lf" in r[1:]]
        assert hits, (rel, lines)


# ---------------------------------------------------------------------------
# 022: Summary Evidence cell names evidence tokens the section bullet carries
# (Rule 7). Tokens: `PR #N` (groups `PR #12/#13`, ranges `PR #3–#8`), a
# backticked SHA with >= 1 letter a–f, `vX.Y` / `vX.Y.Z`, `baseline`.
# ---------------------------------------------------------------------------


def _ev_md(cell, section="PR #22", status="accepted", tracked=None):
    """Anchor F-001 plus F-002 under test: Summary Evidence cell `cell`;
    section Evidence bullet `section` (status permitting); Tracked override."""
    base = status.split()[0]
    labels = _required(base)
    f2 = _row("F-002", "Under test", status, labels)
    if "Evidence" in labels and section is not None:
        f2["bullets"]["Evidence"] = section
    if tracked is not None:
        f2["bullets"]["Tracked"] = tracked
    feats = [_anchor(), f2]
    rows = summary_rows(feats)
    rows[1] = f"| F-002 | Under test | EPUB processing | {status} | {cell} |"
    return md_doc(features=feats, summary=rows), rows[1]


def _f2_heading_line(md):
    return next(i + 1 for i, ln in enumerate(md.split("\n")) if ln.startswith("#### F-002 "))


def test_e1_empty_summary_evidence_cell(script):
    md, row = _ev_md("", section="PR #22")
    errors = row_errors(script, md)
    line = _line_of(md, row)
    assert any(
        "F-002" in e and "Summary Evidence cell" in e and f"line {line}" in e and "empty" in e
        for e in errors
    ), errors


@pytest.mark.parametrize(
    "cell, status",
    [
        ("011", "accepted"),
        ("debt #21", "stub"),
        ("tracked #58", "accepted"),
        ("20260817", "accepted"),
        ("`2026081`", "accepted"),
        ("v1", "accepted"),
    ],
    ids=["branch-only", "debt-on-stub", "tracked-on-accepted", "bare-date", "all-digit-sha", "v1"],
)
def test_e2_cell_without_token_is_rejected(script, cell, status):
    md, row = _ev_md(cell, section=f"{cell} · PR #22", status=status)
    errors = row_errors(script, md)
    line = _line_of(md, row)
    assert any(
        "F-002" in e and f"line {line}" in e and "no evidence token" in e and repr(cell) in e
        for e in errors
    ), errors


@pytest.mark.parametrize(
    "cell, section",
    [
        ("PR #22", "PR #22"),
        ("`b8e0353`", "fix (`b8e0353`)"),
        ("v1.5.0", "v1.5.0"),
        ("baseline", "baseline"),
        ("PR #12/#13", "004 (PR #12/#13)"),
        ("PR #3–#8", "002 · PR #3–#8"),
        ("PR #3-#8", "002 · PR #3-#8"),
        ("011 · PR #22", "011 (PR #22)"),
    ],
    ids=["pr", "sha", "tag", "baseline", "pr-group", "pr-range-en-dash", "pr-range-hyphen", "context-plus-pr"],
)
def test_e3_cell_with_token_present_in_section_is_clean(script, cell, section):
    md, _ = _ev_md(cell, section=section)
    assert row_errors(script, md) == []


@pytest.mark.parametrize("status", ["superseded → F-001", "removed"])
def test_e4_retired_rows_need_a_token_too(script, status):
    md, row = _ev_md("011", section="011", status=status)
    errors = row_errors(script, md)
    line = _line_of(md, row)
    assert any(
        "F-002" in e and f"line {line}" in e and "no evidence token" in e and "'011'" in e
        for e in errors
    ), errors
    md, _ = _ev_md("PR #5", section="removal PR #5", status=status)
    assert row_errors(script, md) == []


@pytest.mark.parametrize(
    "cell, tracked",
    [
        ("tracked #58", "debt #58 → 018-library-routes"),
        ("tracked 018", "plan 018-library-routes"),
    ],
    ids=["debt-ref", "branch-ref"],
)
def test_e5_absent_tracked_cell_is_clean(script, cell, tracked):
    md, _ = _ev_md(cell, status="absent", tracked=tracked)
    assert row_errors(script, md) == []


@pytest.mark.parametrize(
    "cell, tracked, quoted",
    [
        ("tracked #59", "debt #58", ["#59"]),
        ("tracked #58", "debt #580", ["#58"]),
        ("tracked 018", "plan 0180", ["018"]),
        ("tracked #58 · PR #5", "debt #58", ["PR #5"]),
        ("", "debt #58", ["empty"]),
    ],
    ids=["wrong-ref", "ref-prefix-of-longer-number", "branch-inside-longer-number", "absent-with-token", "empty"],
)
def test_e5_absent_tracked_cell_defects(script, cell, tracked, quoted):
    md, row = _ev_md(cell, status="absent", tracked=tracked)
    errors = row_errors(script, md)
    line = _line_of(md, row)
    assert any(
        "F-002" in e and "Summary Evidence cell" in e and f"line {line}" in e and all(q in e for q in quoted)
        for e in errors
    ), errors


@pytest.mark.parametrize(
    "cell, section, token",
    [
        ("PR #23", "PR #22", "PR #23"),
        ("PR #22 · `abc1234`", "PR #22", "`abc1234`"),
        ("PR #22 · baseline", "PR #22", "baseline"),
    ],
    ids=["pr", "sha", "baseline"],
)
def test_e6_cell_token_missing_from_section(script, cell, section, token):
    md, row = _ev_md(cell, section=section)
    errors = row_errors(script, md)
    line, heading = _line_of(md, row), _f2_heading_line(md)
    assert len(errors) == 1, errors
    e = errors[0]
    assert "F-002" in e and f"cites {token}," in e, e
    assert f"line {line}" in e and f"heading line {heading}" in e, e


@pytest.mark.parametrize(
    "cell, section",
    [
        ("PR #5", "002 · PR #3–#8"),
        ("PR #3–#8", "PR #3/#4/#5/#6/#7/#8"),
        ("PR #22", "011 (PR #22) · fix PR #26 (`4d3c5ac`) · v1.5.0 · baseline"),
    ],
    ids=["pr-inside-range", "range-vs-group", "section-has-more"],
)
def test_e6_cell_tokens_covered_by_section(script, cell, section):
    md, _ = _ev_md(cell, section=section)
    assert row_errors(script, md) == []


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data_=st.data())
def test_e7_subset_law(script, data_):
    s_tokens = sorted(data_.draw(st.sets(st_ev_token, min_size=1, max_size=6), label="S"))
    t_tokens = data_.draw(
        st.lists(st.sampled_from(s_tokens), min_size=1, unique=True), label="T"
    )
    section = " · ".join(s_tokens)
    md, _ = _ev_md(" · ".join(t_tokens), section=section)
    assert row_errors(script, md) == []

    x = data_.draw(st_ev_token.filter(lambda tok: tok not in s_tokens), label="x")
    md, _ = _ev_md(" · ".join(t_tokens + [x]), section=section)
    errors = row_errors(script, md)
    assert len(errors) == 1, (x, errors)
    assert "F-002" in errors[0] and f"cites {x}," in errors[0], errors


def test_e8_real_ledger_validates_clean(script):
    md = (REPO_ROOT / "docs" / "feature-ledger.md").read_text(encoding="utf-8")
    _, errors = script.validate(md, REPO_ROOT)
    assert errors == []
    assert script.run(REPO_ROOT, check=True) == 0

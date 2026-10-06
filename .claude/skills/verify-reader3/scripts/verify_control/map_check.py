"""`map check`: the skill's feature map against the ledger, and its quoted commands against the parser.

Read-only. Every malformation is reported once and independently as
`{file, kind, message}` (`file` is repo-relative). Commands are collected from fenced
lines and inline backtick spans (headings and `$B` lines skipped) of SKILL.md, the map
README and every map file. A candidate whose first token (after an optional `python3`)
ends in `control.py` is parsed, never dispatched, by the CLI's real parser.
"""

import contextlib
import io
import os
import re
import shlex

FEAT_REL = ".claude/skills/verify-reader3/references/features"
README_REL = FEAT_REL + "/README.md"
SKILL_REL = ".claude/skills/verify-reader3/SKILL.md"
LEDGER_REL = "docs/feature-ledger.md"
FOUR_H2 = ["Sub-features", "How to get to it (user POV)", "Driving it with control.py and $B", "Gotchas"]
_MAP_NAME = re.compile(r"F-\d{3}\.md")
_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
_SPAN = re.compile(r"`([^`\n]+)`")


def _problem(file, kind, message):
    return {"file": file, "kind": kind, "message": message}


def _fence_marker(stripped):
    for m in ("```", "~~~"):
        if stripped.startswith(m):
            return m
    return None


def scan(text):
    """Yield `(lineno, line, in_fence)` for non-fence-delimiter lines."""
    fence = None
    for n, line in enumerate(text.split("\n"), 1):
        stripped = line.strip()
        marker = _fence_marker(stripped)
        if fence is None and marker:
            fence = marker
            continue
        if fence is not None and marker == fence:
            fence = None
            continue
        yield n, line, fence is not None


def _body_lines(text):
    """Lines after an optional `---` front matter block."""
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return lines[i + 1:]
    return lines


def _h1_problems(rel, fid, text):
    first = next((ln for ln in _body_lines(text) if ln.strip()), "")
    if not first.startswith("# "):
        return [_problem(rel, "no_h1", f"{rel} must start with a `# {fid} ...` title")]
    words = first[2:].split()
    if not words or words[0] != fid:
        return [_problem(rel, "h1_mismatch", f"{rel} title {first.strip()!r} must start with {fid}")]
    return []


def _link_problems(rel, fid, text, root):
    links = []
    for _, line, in_fence in scan(text):
        if not in_fence:
            links += [(t, href) for t, href in _LINK.findall(line) if href.split("#", 1)[0].endswith("feature-ledger.md")]
    if not links:
        return [_problem(rel, "no_ledger_link", f"{rel} has no link to {LEDGER_REL}")]
    out = []
    label, href = links[0]
    target = os.path.normpath(os.path.join(os.path.dirname(os.path.join(root, rel)), href.split("#", 1)[0]))
    if target != os.path.normpath(os.path.join(root, LEDGER_REL)):
        out.append(_problem(rel, "ledger_link_broken", f"{rel} links {href}, which does not resolve to {LEDGER_REL}"))
    if label.strip() != fid:
        out.append(_problem(rel, "id_mismatch", f"{rel} ledger link text {label!r} must be {fid}"))
    return out


def _h2_problems(rel, text):
    found = [line[3:].strip() for _, line, in_fence in scan(text) if not in_fence and line.startswith("## ")]
    if found != FOUR_H2:
        return [_problem(rel, "h2_mismatch", f"{rel} H2s are {found}; expected exactly {FOUR_H2} in that order")]
    return []


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def candidates(text):
    """`(lineno, candidate)` command candidates in a markdown text."""
    out = []
    for n, line, in_fence in scan(text):
        stripped = line.strip()
        if in_fence:
            if stripped and not stripped.startswith("$B"):
                out.append((n, stripped))
        elif not stripped.startswith("#") and not stripped.startswith("$B"):
            out += [(n, span.strip()) for span in _SPAN.findall(line)]
    return out


def control_args(candidate):
    """The argv after `control.py`, or None when the candidate is not a control.py command."""
    try:
        tokens = shlex.split(candidate, comments=True)
    except ValueError:
        tokens = candidate.split()
    i = 1 if tokens and tokens[0] in ("python3", "python") else 0
    if len(tokens) <= i or not tokens[i].endswith("control.py"):
        return None
    return tokens[i + 1:]


def check_args(args):
    """The parser's complaint about `args`, or None when they parse. Never dispatches."""
    from verify_control import cli  # cli imports the command modules, so import late
    from verify_control.registry import UsageError

    parser = cli.build_parser()
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            _, extras = parser.parse_known_args(list(args))
    except UsageError as exc:
        return exc.message
    except SystemExit as exc:
        return None if exc.code in (0, None) else f"argparse exited {exc.code}"
    if extras:
        return "unrecognized arguments: " + " ".join(extras)
    return None


def check_command_line(line):
    args = control_args(line)
    return None if args is None else check_args(args)


def _commands(rel, text, dead):
    checked = 0
    for n, cand in candidates(text):
        args = control_args(cand)
        if args is None:
            continue
        checked += 1
        msg = check_args(args)
        if msg:
            dead.append({"file": rel, "line": n, "command": cand, "message": msg})
    return checked


def _map_file_problems(rel, fid, text, root, features, is_absent):
    out = []
    if fid not in features:
        out.append(_problem(rel, "unknown_id", f"{fid} is not a ledger row"))
    elif is_absent(features[fid]):
        out.append(_problem(rel, "absent_row", f"{fid} is an absent row; it must not have a map file"))
    out += _h1_problems(rel, fid, text)
    out += _link_problems(rel, fid, text, root)
    out += _h2_problems(rel, text)
    return out


def check(root, features, is_absent):
    """The `map check` data dict for the tree under `root` and the parsed ledger `features`."""
    root = str(root)
    excluded = sorted(i for i, f in features.items() if is_absent(f))
    problems, dead, mapped, checked = [], [], [], 0
    sources = []
    skill = os.path.join(root, SKILL_REL)
    if os.path.isfile(skill):
        sources.append((SKILL_REL, _read(skill)))
    feat_dir = os.path.join(root, FEAT_REL)
    if not os.path.isdir(feat_dir):
        problems.append(_problem(FEAT_REL, "features_dir_missing", f"{FEAT_REL}/ does not exist"))
    else:
        names = sorted(os.listdir(feat_dir))
        map_files = [n for n in names if _MAP_NAME.fullmatch(n)]
        for n in names:
            if n.endswith(".md") and n != "README.md" and n not in map_files:
                problems.append(_problem(f"{FEAT_REL}/{n}", "bad_filename", f"{n} is not named F-NNN.md"))
        for n in map_files:
            rel, fid = f"{FEAT_REL}/{n}", n[:-3]
            text = _read(os.path.join(feat_dir, n))
            sources.append((rel, text))
            problems += _map_file_problems(rel, fid, text, root, features, is_absent)
            if fid in features and not is_absent(features[fid]):
                mapped.append(fid)
        readme = os.path.join(feat_dir, "README.md")
        if not os.path.isfile(readme):
            problems.append(_problem(README_REL, "readme_missing", f"{README_REL} does not exist"))
        else:
            text = _read(readme)
            sources.append((README_REL, text))
            problems += [_problem(README_REL, "readme_missing_entry", f"{README_REL} does not list {n}")
                         for n in map_files if n not in text]
    for rel, text in sources:
        checked += _commands(rel, text, dead)
    mapped = sorted(mapped)
    missing = sorted(i for i, f in features.items() if not is_absent(f) and i not in mapped)
    return {"rows": len(features), "mapped": mapped, "excluded": excluded, "missing": missing,
            "problems": problems, "dead_commands": dead, "commands_checked": checked}

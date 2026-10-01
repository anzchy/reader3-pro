"""018 WI-3 / WI-1: the settings revision and the If-Match evaluator.

Matrix cases R3-1-01 .. R3-1-08 and R3-1-21
(``.claude/tdd-guardian/tests-20261001-114124.md``).

``settings_revision`` is the ETag of ``config/ai_settings.json``. It is an
HMAC-SHA256 under a per-process ``secrets.token_bytes(32)`` key, not a bare
sha256: ``/api/*`` has no authentication, and every byte of the file except the
API keys can be rebuilt from GET + export, so a bare digest would be an offline
oracle for a guessed or leaked key. The ``file:`` / ``absent`` framing keeps an
empty file and a missing file apart.

``if_match_satisfied`` is RFC 7232 strong comparison over a comma list. Weak
tags never match, ``*`` always matches, and anything malformed -- including any
empty list element (coordinator ruling 3) -- raises ``ValueError`` rather than
returning a boolean, so the route can answer 400 instead of guessing.

Nothing here touches the filesystem except the two subprocess cases, which
point ``READER3_AI_SETTINGS`` into ``tmp_path`` and run with ``cwd=tmp_path``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from reader3_app.ai.config import if_match_satisfied, settings_revision

HEX64 = re.compile(r"[0-9a-f]{64}")


# --------------------------------------------------------------------------
# R3-1-01 -- S2: shape for present, empty and absent input
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [None, b"", b"{", b'{"providers": {}}'],
    ids=["absent", "empty", "one-byte", "small-object"],
)
def test_revision_is_64_lowercase_hex(raw) -> None:
    rev = settings_revision(raw)
    assert isinstance(rev, str)
    assert re.fullmatch(r"[0-9a-f]{64}", rev), rev


# --------------------------------------------------------------------------
# R3-1-02 -- S4: determinism, sensitivity, domain separation
# --------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(a=st.binary(max_size=512), b=st.binary(max_size=512))
@example(a=b"", b=b"absent")
@example(a=b"absent", b=b"file:")
@example(a=b"file:", b=b"")
def test_revision_law(a: bytes, b: bytes) -> None:
    assert settings_revision(a) == settings_revision(a), "not deterministic"
    if a != b:
        assert settings_revision(a) != settings_revision(b), (a, b)
    absent = settings_revision(None)
    assert absent != settings_revision(a), f"absent collides with present input {a!r}"
    assert absent != settings_revision(b), f"absent collides with present input {b!r}"


# --------------------------------------------------------------------------
# R3-1-03 -- S3: not an offline oracle
# --------------------------------------------------------------------------


def test_revision_is_not_bare_sha256() -> None:
    raw = b'{"providers": {"anthropic": {"api_key": "sk-x"}}}'
    rev = settings_revision(raw)
    offline = {
        hashlib.sha256(raw).hexdigest(),
        hashlib.sha256(b"file:" + raw).hexdigest(),
        hmac.new(b"", b"file:" + raw, hashlib.sha256).hexdigest(),
    }
    assert rev not in offline, "the revision can be recomputed from the file bytes alone"
    assert settings_revision(None) != hashlib.sha256(b"absent").hexdigest()
    assert rev != hashlib.sha256(b"absent").hexdigest()


# --------------------------------------------------------------------------
# R3-1-04 -- S3: the key is per-process random
# --------------------------------------------------------------------------


_PRINT_SAME = (
    "from reader3_app.ai.config import settings_revision; "
    "print(settings_revision(b'same'))"
)


def _child_env(tmp_path: Path) -> dict:
    return {**os.environ, "READER3_AI_SETTINGS": str(tmp_path / "cfg" / "ai_settings.json")}


def test_revision_key_differs_between_processes(tmp_path: Path) -> None:
    outs: List[str] = []
    for _ in range(2):
        proc = subprocess.run(
            [sys.executable, "-c", _PRINT_SAME],
            capture_output=True,
            text=True,
            timeout=30,
            env=_child_env(tmp_path),
            cwd=tmp_path,
        )
        assert proc.returncode == 0, proc.stderr
        out = proc.stdout.strip()
        assert HEX64.fullmatch(out), out
        outs.append(out)

    assert outs[0] != outs[1], "two processes produced the same revision: the key is not random"
    here = settings_revision(b"same")
    assert here not in outs, "a child process reproduced this process's revision"
    assert not (tmp_path / "cfg").exists(), "importing the config module created files"


# --------------------------------------------------------------------------
# R3-1-21 -- S3: the key is exactly secrets.token_bytes(32), the MAC framing is exact
# --------------------------------------------------------------------------


_FAKE_SECRETS_SCRIPT = """
import json, secrets
calls = []
def fake(n=None):
    calls.append(n)
    return b"\\x07" * n
secrets.token_bytes = fake
from reader3_app.ai import config
print(json.dumps({"calls": calls,
                  "file_x": config.settings_revision(b"x"),
                  "absent": config.settings_revision(None)}))
"""


def test_revision_is_hmac_sha256_over_prefixed_input_with_a_32_byte_secrets_key(
    tmp_path: Path,
) -> None:
    proc = subprocess.run(
        [sys.executable, "-c", _FAKE_SECRETS_SCRIPT],
        capture_output=True,
        text=True,
        timeout=30,
        env=_child_env(tmp_path),
        cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout.strip().splitlines()[-1])

    key = b"\x07" * 32
    assert out["calls"] == [32], out["calls"]
    assert out["file_x"] == hmac.new(key, b"file:x", hashlib.sha256).hexdigest()
    assert out["absent"] == hmac.new(key, b"absent", hashlib.sha256).hexdigest()
    assert not (tmp_path / "cfg").exists(), "importing the config module created files"


# --------------------------------------------------------------------------
# R3-1-05 -- S1: evaluator example table
# --------------------------------------------------------------------------

C = "a" * 64
O = "b" * 64  # noqa: E741 - the matrix's name for "other"


@pytest.mark.parametrize(
    "header, expected",
    [
        (f'"{C}"', True),
        (f'"{O}"', False),
        (f'"{O}", "{C}"', True),
        (f'"{O}","{C}"', True),
        (f'  "{C}"  ', True),
        ("*", True),
        (f'W/"{C}"', False),
        (f'W/"{C}", "{O}"', False),
        (f'W/"{O}", "{C}"', True),
    ],
    ids=[
        "strong-match",
        "strong-mismatch",
        "list-match-second",
        "list-no-space",
        "surrounding-whitespace",
        "star",
        "weak-never-matches",
        "weak-match-plus-strong-other",
        "weak-other-plus-strong-match",
    ],
)
def test_if_match_table(header: str, expected: bool) -> None:
    assert if_match_satisfied(header, C) is expected


# --------------------------------------------------------------------------
# R3-1-06 -- S3: malformed headers raise ValueError (G10 rows included)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "header",
    [
        "",
        "   ",
        C,
        f'"{C}',
        f'"{C}",',
        f', "{C}"',
        f'*, "{C}"',
        "W/",
        f'"{C}" "{O}"',
        f'"{O}",,"{C}"',
        f'"{O}", ,"{C}"',
        '"a b"',
        '"a\x01b"',
        '"a\x7fb"',
    ],
    ids=[
        "empty",
        "whitespace-only",
        "unquoted",
        "unterminated",
        "trailing-comma",
        "leading-comma",
        "star-mixed-with-tags",
        "weak-prefix-alone",
        "missing-comma",
        "empty-interior-element",
        "whitespace-only-interior-element",
        "space-inside-tag",
        "control-char-inside-tag",
        "del-inside-tag",
    ],
)
def test_if_match_malformed_raises(header: str) -> None:
    with pytest.raises(ValueError):
        if_match_satisfied(header, C)


# --------------------------------------------------------------------------
# R3-1-07 -- S4: evaluator law over generated tag lists
# --------------------------------------------------------------------------

hex64 = st.text(alphabet="0123456789abcdef", min_size=64, max_size=64)


@st.composite
def current_and_tags(draw) -> Tuple[str, List[Tuple[bool, str]]]:
    current = draw(hex64)
    tags = draw(
        st.lists(
            st.tuples(st.booleans(), st.one_of(st.just(current), hex64)),
            min_size=1,
            max_size=6,
        )
    )
    return current, tags


def _render(tags: List[Tuple[bool, str]], sep: str = ", ") -> str:
    return sep.join(("W/" if weak else "") + f'"{v}"' for weak, v in tags)


@settings(max_examples=200, deadline=None)
@given(case=current_and_tags())
def test_if_match_law(case) -> None:
    current, tags = case
    header = _render(tags)
    expected = any(not weak and v == current for weak, v in tags)
    assert if_match_satisfied(header, current) == expected, header


# --------------------------------------------------------------------------
# R3-1-08 -- S6: metamorphic -- reorder, duplicate, re-space
# --------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(case=current_and_tags(), data=st.data())
def test_if_match_metamorphic(case, data) -> None:
    current, tags = case
    permuted = list(data.draw(st.permutations(tags)))
    dup_index = data.draw(st.integers(min_value=0, max_value=len(permuted) - 1))
    permuted.append(permuted[dup_index])
    sep = data.draw(st.sampled_from([",", ", ", " ,  ", ",\t"]))

    h1 = _render(tags)
    h2 = _render(permuted, sep)
    assert if_match_satisfied(h1, current) == if_match_satisfied(h2, current), (h1, h2)

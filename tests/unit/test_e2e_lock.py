"""021 WI-1：`scripts/e2e_lock.py` —— 把 e2e lane 命令包在一把 fcntl 锁里跑。

多个会话 / worktree 同时跑 e2e 会互相抢 CPU、抢浏览器，flaky 被放大成「随机红」。包装器的
职责只有一件：**同一时刻至多一个 e2e 在跑**，抢不到就立刻以 75（BUSY）退出并报出持有者，
绝不排队、绝不等待。

律（矩阵 run mode / status / CI bypass 三段）：

* **(L1) 互斥**：存在持有者时，第二个包装器不运行它的 cmd，立刻 rc 75。
* **(L2) 任意结束都释放**：正常退出、非零退出、子进程被 SIGKILL、包装器自己被 SIGKILL ——
  之后下一次 acquire 都成功，且锁文件 inode 不变（从不 unlink）。
* **(L3) 非持有者从不写**：BUSY 尝试与 `status` 探测都不改持有者文件的任何一个字节。
* **(L4) 退出码直通**：子进程正常退出码 k（0..255）→ 包装器 rc == k。
* owner 行组成律：恰好一行四字段 `session= sha= start= pid=`，session 非空且不含空白。
* `status` 是纯观察者：不创建、不修改，答案只取决于有没有 flock 持有者，与 owner 行内容无关。
* CI（`GITHUB_ACTIONS` 非空）run 模式守恒：从不打开 / 创建 / 加锁锁路径。

全部用例走真进程、真 `flock`、真 git、真文件系统，没有 mock。每个 subprocess 调用 / wait
都带显式 timeout（≤30s）；就绪靠 marker 文件 + 轮询截止时间，从不固定 sleep；`finally` 里按
进程组 / pid 清理残留进程。任何用例都不会解析到真实的 `~/.cache`（A16 把 `HOME` 指向 tmp）。

矩阵：`.claude/tdd-guardian/tests-20261001-090925.md` rev 3 的 A1–A16、B1–B3、C1–C9、D1–D5、E1（WI-1）与 F1–F7（WI-2，信号转发）。
"""

from __future__ import annotations

import contextlib
import fcntl
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Optional

import pytest
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "e2e_lock.py"

OWNER_RE = re.compile(r"^session=(\S+) sha=([0-9a-f]{40}|unknown) start=(\d+) pid=(\d+)\n$")
KNOWN = "session=T sha=abc start=1 pid=1\n"
TIMEOUT = 30.0
READY_DEADLINE = 20.0

#: 一个会阻塞到被杀（或 25s 自然超时）的子进程体，先把自己的 pid 写进 marker。
_BLOCK_WRITING_PID = """
import os, time
open({m!r}, 'w').write(str(os.getpid()))
d = time.monotonic() + 25
while time.monotonic() < d:
    time.sleep(0.05)
"""


# ---------------------------------------------------------------- harness


def _env(lock: Optional[Path], **overrides: Optional[str]) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("GITHUB_ACTIONS", None)
    env.pop("READER3_E2E_SESSION", None)
    if lock is not None:
        env["READER3_E2E_LOCK"] = str(lock)
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def _argv(*args: str) -> list[str]:
    return [sys.executable, str(SCRIPT), *args]


def _py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def _run(
    args: list[str], env: dict[str, str], cwd: Path = REPO_ROOT
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _argv(*args), env=env, cwd=str(cwd), capture_output=True, text=True, timeout=TIMEOUT, check=False
    )


def _status(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return _run(["status"], env)


def _popen(args: list[str], env: dict[str, str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        _argv(*args),
        env=env,
        cwd=str(REPO_ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _wait_for(path: Path, proc: Optional[subprocess.Popen[bytes]] = None) -> str:
    """轮询到 marker 出现且非空为止；截止时间到了就判失败（不是固定 sleep）。"""
    deadline = time.monotonic() + READY_DEADLINE
    while time.monotonic() < deadline:
        if path.exists():
            text = path.read_text(encoding="utf-8")
            if text:
                return text
        if proc is not None and proc.poll() is not None:
            pytest.fail(f"进程在 {path.name} 出现之前就退出了，rc={proc.returncode}")
        time.sleep(0.01)
    pytest.fail(f"{READY_DEADLINE}s 内没等到 marker {path}")


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(proc.pid, signal.SIGKILL)
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=TIMEOUT)


def _kill_pid(pid: Optional[int]) -> None:
    if pid is None:
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.kill(pid, signal.SIGKILL)


@contextlib.contextmanager
def _holder(lock: Path, content: str) -> Iterator[int]:
    """测试进程自己当持有者：open → write 已知行 → flock(LOCK_EX)。"""
    fd = os.open(str(lock), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        if content:
            os.write(fd, content.encode("utf-8"))
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield fd
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _head_sha() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10, check=True
    )
    return out.stdout.strip()


def _owner(lock: Path) -> re.Match[str]:
    text = lock.read_bytes().decode("utf-8")
    m = OWNER_RE.fullmatch(text)
    assert m is not None, f"锁文件不是一条合法 owner 行：{text!r}"
    return m


def _still_held(lock: Path) -> bool:
    fd = os.open(str(lock), os.O_RDONLY)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def _snapshot(path: Path) -> tuple[bytes, int, int]:
    st_ = path.stat()
    return path.read_bytes(), st_.st_ino, st_.st_mtime_ns


def _assert_free(env: dict[str, str]) -> None:
    res = _status(env)
    assert (res.returncode, res.stdout) == (0, "FREE\n"), res.stdout + res.stderr


# ---------------------------------------------------------------- run mode


def test_a1_free_path_writes_well_formed_owner_line(tmp_path: Path) -> None:
    lock, marker = tmp_path / "x.lock", tmp_path / "m"
    env = _env(lock, READER3_E2E_SESSION="sessA")
    t0 = int(time.time())
    proc = subprocess.Popen(
        _argv("--", *_py(f"open({str(marker)!r},'w').write('ran')")),
        env=env,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        out, err = proc.communicate(timeout=TIMEOUT)
    finally:
        _kill_pid(proc.pid if proc.poll() is None else None)
    t1 = math.ceil(time.time())
    assert proc.returncode == 0, err
    assert (out, err) == ("", "")
    assert marker.read_text(encoding="utf-8") == "ran"
    m = _owner(lock)
    assert m.group(1) == "sessA"
    assert m.group(2) == _head_sha()
    assert t0 <= int(m.group(3)) <= t1
    assert int(m.group(4)) == proc.pid, "pid= 必须是包装器自己的 pid，不是子进程的"


def test_a2_owner_line_is_on_disk_before_child_starts(tmp_path: Path) -> None:
    lock, marker = tmp_path / "x.lock", tmp_path / "m"
    env = _env(lock, READER3_E2E_SESSION="ord")
    code = f"import os; open({str(marker)!r},'w').write(open(os.environ['READER3_E2E_LOCK']).read())"
    proc = subprocess.Popen(_argv("--", *_py(code)), env=env, cwd=str(REPO_ROOT))
    try:
        rc = proc.wait(timeout=TIMEOUT)
    finally:
        _kill_pid(proc.pid if proc.poll() is None else None)
    assert rc == 0
    seen = marker.read_text(encoding="utf-8")
    m = OWNER_RE.fullmatch(seen)
    assert m is not None, f"子进程启动时看到的锁文件不是完整 owner 行：{seen!r}"
    assert m.group(1) == "ord"
    assert int(m.group(4)) == proc.pid
    assert seen == lock.read_text(encoding="utf-8")


@settings(deadline=None, max_examples=25, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(k=st.integers(0, 255))
@example(k=0)
@example(k=1)
@example(k=5)
@example(k=2)
@example(k=75)
@example(k=126)
@example(k=127)
@example(k=128)
@example(k=130)
@example(k=255)
def test_a3_exit_code_passthrough_over_0_255(k: int) -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        res = _run(["--", *_py(f"raise SystemExit({k})")], _env(tmp / "x.lock"))
        assert res.returncode == k, res.stderr
        if k == 75:
            assert not res.stderr.startswith("BUSY "), "子进程自己退 75 不能被说成 BUSY"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_a4_busy_against_test_process_holder_fails_fast(tmp_path: Path) -> None:
    lock, marker = tmp_path / "x.lock", tmp_path / "m"
    env = _env(lock)
    with _holder(lock, KNOWN):
        t = time.monotonic()
        res = _run(["--", *_py(f"open({str(marker)!r},'w')")], env)
        elapsed = time.monotonic() - t
    assert res.returncode == 75, res.stdout + res.stderr
    assert res.stderr.rstrip("\n") == "BUSY session=T sha=abc start=1 pid=1"
    assert res.stdout == ""
    assert elapsed < 2.0, f"非空 owner 行不该重试/等待：{elapsed:.2f}s"
    assert not marker.exists(), "BUSY 时 cmd 被运行了"


def test_a5_busy_against_empty_holder_file_reports_owner_unknown(tmp_path: Path) -> None:
    lock, marker = tmp_path / "x.lock", tmp_path / "m"
    env = _env(lock)
    with _holder(lock, ""):
        t = time.monotonic()
        res = _run(["--", *_py(f"open({str(marker)!r},'w')")], env)
        elapsed = time.monotonic() - t
        size = lock.stat().st_size
    assert res.returncode == 75, res.stdout + res.stderr
    assert res.stderr.rstrip("\n") == "BUSY (owner unknown)"
    assert elapsed < 10.0
    assert not marker.exists()
    assert size == 0


def test_a6_mutual_exclusion_between_two_real_wrappers(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    ready_a, release, ran_b = tmp_path / "readyA", tmp_path / "R", tmp_path / "ranB"
    child_a = (
        "import os, time\n"
        f"open({str(ready_a)!r}, 'w').write('x')\n"
        "d = time.monotonic() + 25\n"
        f"while not os.path.exists({str(release)!r}) and time.monotonic() < d:\n"
        "    time.sleep(0.01)\n"
    )
    a = _popen(["--", *_py(child_a)], _env(lock, READER3_E2E_SESSION="A"))
    try:
        _wait_for(ready_a, a)
        env_b = _env(lock, READER3_E2E_SESSION="B")
        cmd_b = ["--", *_py(f"open({str(ran_b)!r},'w')")]
        t = time.monotonic()
        first = _run(cmd_b, env_b)
        elapsed = time.monotonic() - t
        assert first.returncode == 75, first.stdout + first.stderr
        assert elapsed < 2.0
        assert first.stderr.startswith("BUSY ")
        owner_text = first.stderr[len("BUSY ") :]
        assert owner_text == lock.read_text(encoding="utf-8")
        m = OWNER_RE.fullmatch(owner_text)
        assert m is not None and m.group(1) == "A" and int(m.group(4)) == a.pid
        assert not ran_b.exists()

        release.write_text("go", encoding="utf-8")
        assert a.wait(timeout=TIMEOUT) == 0
        retry = _run(cmd_b, env_b)
        assert retry.returncode == 0, retry.stderr
        assert ran_b.exists()
        assert _owner(lock).group(1) == "B"
    finally:
        _kill_group(a)


def test_a7_non_holders_never_change_a_byte_of_the_holder_file(tmp_path: Path) -> None:
    lock, marker = tmp_path / "x.lock", tmp_path / "m"
    env = _env(lock)
    line = "session=" + "x" * 180 + " sha=abc start=1 pid=1\n"
    assert len(line.encode()) >= 200
    with _holder(lock, line):
        before = lock.read_bytes()
        inode = lock.stat().st_ino
        for op in ("busy", "status") * 3:
            if op == "busy":
                res = _run(["--", *_py(f"open({str(marker)!r},'w')")], env)
                assert res.returncode == 75, res.stderr
            else:
                res = _status(env)
                assert res.returncode == 1, res.stdout + res.stderr
            assert lock.read_bytes() == before, f"{op} 改了持有者的文件"
            assert lock.stat().st_ino == inode
    assert not marker.exists()


@pytest.mark.parametrize("mode", ["exit0", "exit3", "child_sigkill", "wrapper_sigkill"])
def test_a8_lock_is_released_after_every_way_a_run_ends(tmp_path: Path, mode: str) -> None:
    lock, marker = tmp_path / "x.lock", tmp_path / "m"
    env = _env(lock)
    seed = _run(["--", *_py("pass")], env)
    assert seed.returncode == 0, seed.stderr
    inode = lock.stat().st_ino

    if mode in ("exit0", "exit3"):
        k = 0 if mode == "exit0" else 3
        res = _run(["--", *_py(f"raise SystemExit({k})")], env)
        assert res.returncode == k, res.stderr
    else:
        wrapper = _popen(["--", *_py(_BLOCK_WRITING_PID.format(m=str(marker)))], env)
        child_pid: Optional[int] = None
        try:
            child_pid = int(_wait_for(marker, wrapper))
            if mode == "child_sigkill":
                os.kill(child_pid, signal.SIGKILL)
                assert wrapper.wait(timeout=TIMEOUT) == 137, "子进程死于 SIGKILL → 128+9"
            else:
                os.kill(wrapper.pid, signal.SIGKILL)
                assert wrapper.wait(timeout=TIMEOUT) == -signal.SIGKILL
                os.kill(child_pid, 0)  # 孤儿子进程还活着
                fresh = _run(["--", *_py("pass")], env)
                assert fresh.returncode == 0, "包装器被 SIGKILL 后锁没释放（锁 fd 被子进程继承了？）" + fresh.stderr
                os.kill(child_pid, 0)  # 证明这次 acquire 发生在孤儿仍存活时
        finally:
            _kill_pid(child_pid)
            _kill_group(wrapper)

    _assert_free(env)
    again = _run(["--", *_py("pass")], env)
    assert again.returncode == 0, again.stderr
    assert lock.is_file()
    assert lock.stat().st_ino == inode, "锁文件被 unlink / 替换过"


def test_a9_repeated_runs_idempotent_and_shorter_line_leaves_no_tail(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    lock.write_text("session=" + "z" * 500 + " sha=unknown start=1 pid=1\nGARBAGE-SECOND-LINE\n", encoding="utf-8")
    inode = lock.stat().st_ino
    last_start = -1
    for n in range(5):
        res = _run(["--", *_py("pass")], _env(lock, READER3_E2E_SESSION=f"r{n}"))
        assert res.returncode == 0, res.stderr
        raw = lock.read_bytes().decode("utf-8")
        m = OWNER_RE.fullmatch(raw)
        assert m is not None, f"第 {n} 次之后不是恰好一条 owner 行：{raw[:120]!r}"
        assert m.group(1) == f"r{n}"
        assert "z" not in raw and "GARBAGE" not in raw
        start = int(m.group(3))
        assert start >= last_start
        last_start = start
        assert lock.stat().st_ino == inode


def test_a10_command_not_found_gives_127_and_releases(tmp_path: Path) -> None:
    env = _env(tmp_path / "x.lock")
    res = _run(["--", "/nonexistent/xyz-021"], env)
    assert res.returncode == 127
    assert res.stderr.strip() != ""
    assert "Traceback" not in res.stderr
    _assert_free(env)


def test_a11_command_not_executable_gives_126_and_releases(tmp_path: Path) -> None:
    env = _env(tmp_path / "x.lock")
    script = tmp_path / "noexec.sh"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o644)
    res = _run(["--", str(script)], env)
    assert res.returncode == 126, res.stderr
    assert "Traceback" not in res.stderr
    _assert_free(env)


def test_a12_missing_parent_directories_are_created(tmp_path: Path) -> None:
    lock = tmp_path / "a" / "b" / "x.lock"
    res = _run(["--", *_py("pass")], _env(lock))
    assert res.returncode == 0, res.stderr
    assert lock.is_file()
    _owner(lock)


def test_a13_directory_at_lock_path_is_rc2_in_run_mode(tmp_path: Path) -> None:
    lock, marker = tmp_path / "x.lock", tmp_path / "m"
    os.mkdir(lock)
    res = _run(["--", *_py(f"open({str(marker)!r},'w')")], _env(lock))
    assert res.returncode == 2
    assert str(lock) in res.stderr
    assert "directory" in res.stderr and "rmdir" in res.stderr
    assert "Traceback" not in res.stderr
    assert not marker.exists()
    assert lock.is_dir() and list(lock.iterdir()) == []


def test_a14_child_shares_the_wrapper_process_group(tmp_path: Path) -> None:
    lock, marker = tmp_path / "x.lock", tmp_path / "m"
    wrapper = _popen(["--", *_py(f"import os; open({str(marker)!r},'w').write(str(os.getpgid(0)))")], _env(lock))
    try:
        assert wrapper.wait(timeout=TIMEOUT) == 0
    finally:
        _kill_group(wrapper)
    assert int(marker.read_text(encoding="utf-8")) == wrapper.pid, "D-1：子进程必须留在包装器的进程组里"


def test_a15_sha_resolves_from_script_repo_even_from_foreign_cwd(tmp_path: Path) -> None:
    probe = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse"], capture_output=True, text=True, timeout=10, check=False
    )
    assert probe.returncode != 0, "前提不成立：tmp_path 落在某个 git 仓库里"
    lock = tmp_path / "x.lock"
    res = _run(["--", *_py("pass")], _env(lock), cwd=tmp_path)
    assert res.returncode == 0, res.stderr
    assert _owner(lock).group(2) == _head_sha()


@pytest.mark.parametrize("variant", ["clean", "legacy_dir"])
def test_a16_default_lock_path_is_home_cache_flock(tmp_path: Path, variant: str) -> None:
    home = tmp_path / "home"
    home.mkdir()
    cache = home / ".cache"
    legacy = cache / "reader3-e2e.lock"
    if variant == "legacy_dir":
        os.makedirs(legacy)
    env = _env(None, READER3_E2E_LOCK=None, HOME=str(home))
    res = _run(["--", *_py("pass")], env)
    assert res.returncode == 0, res.stderr
    flock_file = cache / "reader3-e2e.flock"
    assert flock_file.is_file()
    _owner(flock_file)
    if variant == "clean":
        assert not legacy.exists()
        assert sorted(p.name for p in cache.iterdir()) == ["reader3-e2e.flock"]
    else:
        assert legacy.is_dir() and list(legacy.iterdir()) == []
        assert sorted(p.name for p in cache.iterdir()) == ["reader3-e2e.flock", "reader3-e2e.lock"]


# ---------------------------------------------------------------- owner line


@settings(deadline=None, max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(session=st.text(alphabet=st.characters(exclude_categories=("Cs",), exclude_characters="\x00"), max_size=40))
@example(session="a b")
@example(session="a\nsession=evil sha=0 start=0 pid=0")
@example(session="\t")
@example(session="x y")
@example(session="\r")
@example(session="plain-Name_1")
def test_b1_session_is_sanitized_to_one_whitespace_free_field(session: str) -> None:
    tmp = Path(tempfile.mkdtemp())
    try:
        lock = tmp / "x.lock"
        res = _run(["--", *_py("pass")], _env(lock, READER3_E2E_SESSION=session))
        assert res.returncode == 0, res.stderr
        text = lock.read_bytes().decode("utf-8")
        assert len(text.splitlines()) == 1 and text.endswith("\n")
        m = OWNER_RE.fullmatch(text)
        assert m is not None, f"owner 行被注入或破坏：{text!r}"
        got = m.group(1)
        assert got and not any(c.isspace() for c in got)
        if session and not any(c.isspace() for c in session):
            assert got == session, "干净的 session 必须原样往返"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.parametrize("value", [None, ""], ids=["unset", "empty"])
def test_b2_unset_and_empty_session_fall_back_to_dash(tmp_path: Path, value: Optional[str]) -> None:
    lock = tmp_path / "x.lock"
    res = _run(["--", *_py("pass")], _env(lock, READER3_E2E_SESSION=value))
    assert res.returncode == 0, res.stderr
    assert _owner(lock).group(1) == "-"


def test_b3_git_unavailable_gives_sha_unknown(tmp_path: Path) -> None:
    lock, empty_bin = tmp_path / "x.lock", tmp_path / "emptybin"
    empty_bin.mkdir()
    res = _run(["--", *_py("pass")], _env(lock, PATH=str(empty_bin)))
    assert res.returncode == 0, res.stderr
    assert "Traceback" not in res.stderr
    assert _owner(lock).group(2) == "unknown"


# ---------------------------------------------------------------- status


def test_c1_status_on_missing_file_is_free_and_creates_nothing(tmp_path: Path) -> None:
    lock = tmp_path / "never.lock"
    before = sorted(tmp_path.iterdir())
    res = _status(_env(lock))
    assert (res.returncode, res.stdout, res.stderr) == (0, "FREE\n", "")
    assert not lock.exists()
    assert sorted(tmp_path.iterdir()) == before


def test_c2_status_with_stale_owner_line_is_plain_free(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    env = _env(lock, READER3_E2E_SESSION="stale")
    assert _run(["--", *_py("pass")], env).returncode == 0
    before = lock.read_bytes()
    res = _status(env)
    assert (res.returncode, res.stdout) == (0, "FREE\n")
    assert lock.read_bytes() == before


def test_c3_status_held_prints_exact_line_and_holder_keeps_lock(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    with _holder(lock, KNOWN):
        res = _status(_env(lock))
        assert _still_held(lock), "status 探测之后持有者丢了锁"
    assert (res.returncode, res.stdout, res.stderr) == (1, "HELD " + KNOWN, "")


def test_c4_status_held_multiline_reports_first_line_only(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    with _holder(lock, KNOWN + "second line\n"):
        res = _status(_env(lock))
    assert (res.returncode, res.stdout) == (1, "HELD " + KNOWN)


def test_c5_status_held_empty_file_reports_owner_unknown(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    with _holder(lock, ""):
        t = time.monotonic()
        res = _status(_env(lock))
        elapsed = time.monotonic() - t
        size = lock.stat().st_size
    assert (res.returncode, res.stdout) == (1, "HELD (owner unknown)\n")
    assert elapsed < 10.0
    assert size == 0


def test_c6_status_on_directory_is_rc2(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    os.mkdir(lock)
    res = _status(_env(lock))
    assert res.returncode == 2
    assert str(lock) in res.stderr
    assert "directory" in res.stderr and "rmdir" in res.stderr
    assert "FREE" not in res.stdout
    assert lock.is_dir() and list(lock.iterdir()) == []


def test_c7_status_ignores_github_actions(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    with _holder(lock, KNOWN):
        res = _status(_env(lock, GITHUB_ACTIONS="true"))
    assert (res.returncode, res.stdout) == (1, "HELD " + KNOWN)


def test_c8_unlocked_file_naming_a_live_pid_is_free(tmp_path: Path) -> None:
    lock = tmp_path / "x.lock"
    lock.write_text(f"session=T sha=abc start=1 pid={os.getpid()}\n", encoding="utf-8")
    before = lock.read_bytes()
    res = _status(_env(lock))
    assert (res.returncode, res.stdout) == (0, "FREE\n"), "status 不能按 pid 存活判断"
    assert lock.read_bytes() == before


def test_c9_held_lock_naming_a_dead_pid_is_held(tmp_path: Path) -> None:
    gone = subprocess.Popen(_py("pass"))
    gone.wait(timeout=TIMEOUT)
    dead = gone.pid
    try:
        os.kill(dead, 0)
    except ProcessLookupError:
        pass
    else:
        pytest.skip(f"pid {dead} 已被复用")
    lock = tmp_path / "x.lock"
    line = f"session=T sha=abc start=1 pid={dead}\n"
    with _holder(lock, line):
        before = lock.read_bytes()
        res = _status(_env(lock))
        assert lock.read_bytes() == before
        assert _still_held(lock)
    assert (res.returncode, res.stdout) == (1, "HELD " + line)


# ---------------------------------------------------------------- CI bypass

_CI_CMD = "open({m!r},'w'); raise SystemExit(5)"


def test_d1_ci_with_held_lock_runs_cmd_and_leaves_holder_untouched(tmp_path: Path) -> None:
    lock, marker = tmp_path / "x.lock", tmp_path / "m"
    with _holder(lock, KNOWN):
        before = _snapshot(lock)
        res = _run(["--", *_py(_CI_CMD.format(m=str(marker)))], _env(lock, GITHUB_ACTIONS="true"))
        after = _snapshot(lock)
    assert res.returncode == 5, res.stderr
    assert marker.exists()
    assert after[:2] == before[:2]


def test_d2_ci_with_directory_at_lock_path_runs_cmd(tmp_path: Path) -> None:
    lock, marker = tmp_path / "x.lock", tmp_path / "m"
    os.mkdir(lock)
    res = _run(["--", *_py(_CI_CMD.format(m=str(marker)))], _env(lock, GITHUB_ACTIONS="true"))
    assert res.returncode == 5, res.stderr
    assert marker.exists()
    assert lock.is_dir() and list(lock.iterdir()) == []


def test_d3_ci_with_absent_lock_path_never_creates_it(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    lock, marker = sub / "x.lock", tmp_path / "m"
    res = _run(["--", *_py(_CI_CMD.format(m=str(marker)))], _env(lock, GITHUB_ACTIONS="true"))
    assert res.returncode == 5, res.stderr
    assert not sub.exists() and not lock.exists()


def test_d4_empty_github_actions_is_not_ci(tmp_path: Path) -> None:
    lock, marker = tmp_path / "x.lock", tmp_path / "m"
    with _holder(lock, KNOWN):
        res = _run(["--", *_py(f"open({str(marker)!r},'w')")], _env(lock, GITHUB_ACTIONS=""))
    assert res.returncode == 75, res.stdout + res.stderr
    assert res.stderr.startswith("BUSY ")
    assert not marker.exists()


def test_d5_ci_with_present_unlocked_file_does_not_take_the_lock(tmp_path: Path) -> None:
    lock, marker = tmp_path / "x.lock", tmp_path / "m"
    lock.write_text("session=seed sha=abc start=1 pid=1\n", encoding="utf-8")
    before = _snapshot(lock)
    code = (
        "import fcntl, os; "
        f"fd = os.open({str(lock)!r}, os.O_RDONLY); "
        "fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); "
        f"open({str(marker)!r}, 'w').write('free')"
    )
    res = _run(["--", *_py(code)], _env(lock, GITHUB_ACTIONS="true"))
    assert res.returncode == 0, res.stderr
    assert marker.read_text(encoding="utf-8") == "free"
    assert _snapshot(lock) == before


# ---------------------------------------------------------------- CLI parsing


@pytest.mark.parametrize(
    "case",
    ["empty", "dashdash_only", "no_dashdash", "no_dashdash_writes_m", "bogus", "status_x", "status_dashdash"],
)
def test_e1_usage_errors_are_rc2_and_touch_no_lock(tmp_path: Path, case: str) -> None:
    lock, marker = tmp_path / "x.lock", tmp_path / "m"
    args = {
        "empty": [],
        "dashdash_only": ["--"],
        "no_dashdash": ["python", "-c", "pass"],
        "no_dashdash_writes_m": _py(f"open({str(marker)!r},'w')"),
        "bogus": ["bogus"],
        "status_x": ["status", "x"],
        "status_dashdash": ["status", "--"],
    }[case]
    res = _run(args, _env(lock))
    assert res.returncode == 2, res.stdout + res.stderr
    assert res.stderr.strip() != ""
    # 「脚本不存在」时 python 解释器自己也退 2、stderr 也非空——要求 stderr 是包装器的用法提示，
    # 免得这条在实现缺席时空转通过（argparse 风格的 `usage:` 同样满足）。
    assert "usage" in res.stderr.lower(), res.stderr
    assert "Traceback" not in res.stderr
    assert res.stdout == ""
    assert not lock.exists()
    assert not marker.exists()


# ---------------------------------------------------------------- WI-2：信号转发与 child-status → rc 映射
#
# 律（矩阵 rev 3 WI-2 段，F1–F7）：
# * (L5) rc 映射是全函数：子进程正常退出 k → 包装器 k；子进程死于信号 N → 包装器 128+N，绝不在
#   自己身上 re-raise。
# * (L6) 生命周期包含：任意次数、任意混合的转发信号之后，包装器（连同锁）都活得比子进程久。
# 信号一律只发给 `wrapper.pid`，从不发给进程组——这样子进程的反应只能由「转发」来解释。
# 矩阵：`.claude/tdd-guardian/tests-20261001-090925.md` 的 F1–F7。

_TRAP_EXIT7 = """
import os, signal, time
def h(s, f):
    open({g!r}, 'w').write('got-' + signal.Signals(s).name)
    os._exit(7)
signal.signal(signal.{sig}, h)
open({m!r}, 'w').write(str(os.getpid()))
d = time.monotonic() + 25
while time.monotonic() < d:
    time.sleep(0.05)
"""

_DEFAULT_BLOCK = """
import os, signal, time
signal.signal(signal.{sig}, signal.SIG_DFL)
open({m!r}, 'w').write(str(os.getpid()))
d = time.monotonic() + 25
while time.monotonic() < d:
    time.sleep(0.05)
"""


def _wait_text(path: Path, expected: str, proc: subprocess.Popen[bytes]) -> None:
    """轮询到文件内容恰好等于 expected；被等的进程先退出就立刻判失败。"""
    deadline = time.monotonic() + READY_DEADLINE
    while time.monotonic() < deadline:
        if path.exists() and path.read_text(encoding="utf-8") == expected:
            return
        if proc.poll() is not None:
            got = path.read_text(encoding="utf-8") if path.exists() else None
            pytest.fail(f"进程在 {path.name} == {expected!r} 之前退出了，rc={proc.returncode}，内容={got!r}")
        time.sleep(0.01)
    pytest.fail(f"{READY_DEADLINE}s 内 {path} 没变成 {expected!r}")


def _pid_or_none(path: Path) -> Optional[int]:
    with contextlib.suppress(OSError, ValueError):
        return int(path.read_text(encoding="utf-8"))
    return None


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT], ids=["SIGTERM", "SIGINT"])
def test_f1_trapping_child_receives_forwarded_signal_and_rc_passes(tmp_path: Path, sig: signal.Signals) -> None:
    lock, marker, got = tmp_path / "x.lock", tmp_path / "m", tmp_path / "g"
    env = _env(lock)
    code = _TRAP_EXIT7.format(g=str(got), m=str(marker), sig=sig.name)
    wrapper = _popen(["--", *_py(code)], env)
    try:
        _wait_for(marker, wrapper)
        os.kill(wrapper.pid, sig)
        rc = wrapper.wait(timeout=TIMEOUT)
        assert rc == 7, f"信号没转发到子进程（或包装器先死了）：rc={rc}"
        assert got.read_text(encoding="utf-8") == f"got-{sig.name}"
    finally:
        _kill_pid(_pid_or_none(marker))
        _kill_group(wrapper)
    _assert_free(env)


@pytest.mark.parametrize(
    ("sig", "expected"), [(signal.SIGTERM, 143), (signal.SIGINT, 130)], ids=["SIGTERM", "SIGINT"]
)
def test_f2_forwarded_signal_kills_default_child_gives_128_plus_n(
    tmp_path: Path, sig: signal.Signals, expected: int
) -> None:
    lock, marker = tmp_path / "x.lock", tmp_path / "m"
    env = _env(lock)
    wrapper = _popen(["--", *_py(_DEFAULT_BLOCK.format(m=str(marker), sig=sig.name))], env)
    try:
        _wait_for(marker, wrapper)
        os.kill(wrapper.pid, sig)
        rc = wrapper.wait(timeout=TIMEOUT)
        assert rc == expected, f"期望 128+{int(sig)}={expected}，得到 {rc}（负数 = 包装器自己死于信号 / re-raise）"
        assert rc > 0
    finally:
        _kill_pid(_pid_or_none(marker))
        _kill_group(wrapper)
    _assert_free(env)


@pytest.mark.parametrize(
    "sig",
    [signal.SIGHUP, signal.SIGINT, signal.SIGKILL, signal.SIGUSR1, signal.SIGUSR2, signal.SIGTERM, signal.SIGALRM],
    ids=lambda s: s.name,
)
def test_f3_rc_mapping_over_the_signal_domain(tmp_path: Path, sig: signal.Signals) -> None:
    lock = tmp_path / "x.lock"
    env = _env(lock)
    reset = "" if sig == signal.SIGKILL else f"signal.signal({int(sig)}, signal.SIG_DFL); "
    res = _run(["--", *_py(f"import os, signal; {reset}os.kill(os.getpid(), {int(sig)})")], env)
    assert res.returncode == 128 + int(sig), res.stderr
    _assert_free(env)


def test_f4_wrapper_waits_out_a_slow_child_and_holds_the_lock(tmp_path: Path) -> None:
    lock, marker, got = tmp_path / "x.lock", tmp_path / "m", tmp_path / "g"
    release, intruder = tmp_path / "R", tmp_path / "X"
    env = _env(lock)
    code = (
        "import os, signal, time\n"
        "flag = []\n"
        "def h(s, f):\n"
        f"    open({str(got)!r}, 'w').write('got')\n"
        "    flag.append(s)\n"
        "signal.signal(signal.SIGTERM, h)\n"
        f"open({str(marker)!r}, 'w').write(str(os.getpid()))\n"
        "d = time.monotonic() + 25\n"
        f"while not (flag and os.path.exists({str(release)!r})) and time.monotonic() < d:\n"
        "    time.sleep(0.01)\n"
        "raise SystemExit(4 if flag else 99)\n"
    )
    wrapper = _popen(["--", *_py(code)], env)
    try:
        _wait_for(marker, wrapper)
        os.kill(wrapper.pid, signal.SIGTERM)
        _wait_text(got, "got", wrapper)
        assert wrapper.poll() is None, "包装器在子进程退出前就退出了"
        held = _status(env)
        assert held.returncode == 1 and held.stdout.startswith("HELD "), held.stdout + held.stderr
        second = _run(["--", *_py(f"open({str(intruder)!r},'w')")], env)
        assert second.returncode == 75, second.stderr
        assert not intruder.exists()
        release.write_text("go", encoding="utf-8")
        assert wrapper.wait(timeout=TIMEOUT) == 4
    finally:
        _kill_pid(_pid_or_none(marker))
        _kill_group(wrapper)
    assert got.read_text(encoding="utf-8") == "got"
    assert not intruder.exists()
    _assert_free(env)


def test_f5_inherited_sig_ign_is_not_passed_to_the_child(tmp_path: Path) -> None:
    lock, marker = tmp_path / "x.lock", tmp_path / "m"
    env = _env(lock)

    def _ignore_int_term() -> None:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)

    code = (
        "import signal, time\n"
        "h = (signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM))\n"
        "names = (getattr(h[0], '__name__', None) or str(h[0]), str(h[1]))\n"
        f"open({str(marker)!r}, 'w').write(repr(names))\n"
        "d = time.monotonic() + 25\n"
        "while time.monotonic() < d:\n"
        "    time.sleep(0.05)\n"
    )
    wrapper = subprocess.Popen(
        _argv("--", *_py(code)),
        env=env,
        cwd=str(REPO_ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        preexec_fn=_ignore_int_term,  # noqa: PLW1509 - 本用例就是要让包装器继承 SIG_IGN
    )
    try:
        seen = _wait_for(marker, wrapper)
        assert seen == repr(("default_int_handler", "Handlers.SIG_DFL")), f"子进程继承到的处置不对：{seen}"
        os.kill(wrapper.pid, signal.SIGTERM)
        assert wrapper.wait(timeout=TIMEOUT) == 143
    finally:
        _kill_group(wrapper)


def test_f6_forwarding_targets_the_child_only_never_the_group(tmp_path: Path) -> None:
    lock, marker, got = tmp_path / "x.lock", tmp_path / "m", tmp_path / "g"
    pid_file, rc_file, launcher_hit = tmp_path / "P", tmp_path / "W", tmp_path / "L"
    env = _env(lock)
    child = _TRAP_EXIT7.format(g=str(got), m=str(marker), sig="SIGTERM")
    launcher_code = (
        "import signal, subprocess, sys\n"
        "def h(s, f):\n"
        f"    open({str(launcher_hit)!r}, 'w').write('launcher-got')\n"
        "signal.signal(signal.SIGTERM, h)\n"
        f"p = subprocess.Popen({_argv('--', *_py(child))!r})\n"
        f"open({str(pid_file)!r}, 'w').write(str(p.pid))\n"
        "rc = p.wait(timeout=60)\n"
        f"open({str(rc_file)!r}, 'w').write(str(rc))\n"
    )
    launcher = subprocess.Popen(
        _py(launcher_code),
        env=env,
        cwd=str(REPO_ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        wrapper_pid = int(_wait_for(pid_file, launcher))
        _wait_for(marker, launcher)
        os.kill(wrapper_pid, signal.SIGTERM)
        assert launcher.wait(timeout=TIMEOUT) == 0
        assert rc_file.read_text(encoding="utf-8") == "7"
        assert got.read_text(encoding="utf-8") == "got-SIGTERM"
        assert not launcher_hit.exists(), "转发打到了整个进程组（killpg / kill(0, …)），而不是只打子进程"
    finally:
        _kill_pid(_pid_or_none(marker))
        _kill_group(launcher)


def test_f7_repeated_and_mixed_signals_are_all_forwarded(tmp_path: Path) -> None:
    lock, marker, got = tmp_path / "x.lock", tmp_path / "m", tmp_path / "g"
    release, intruder = tmp_path / "R", tmp_path / "X"
    env = _env(lock)
    code = (
        "import os, signal, time\n"
        "count = [0]\n"
        "def h(s, f):\n"
        "    count[0] += 1\n"
        f"    open({str(got)!r}, 'w').write(str(count[0]))\n"
        "signal.signal(signal.SIGTERM, h)\n"
        "signal.signal(signal.SIGINT, h)\n"
        f"open({str(marker)!r}, 'w').write(str(os.getpid()))\n"
        "d = time.monotonic() + 25\n"
        f"while not (count[0] >= 3 and os.path.exists({str(release)!r})) and time.monotonic() < d:\n"
        "    time.sleep(0.01)\n"
        "raise SystemExit(4 if count[0] >= 3 else 99)\n"
    )
    wrapper = _popen(["--", *_py(code)], env)
    try:
        _wait_for(marker, wrapper)
        for sig, n in ((signal.SIGTERM, "1"), (signal.SIGTERM, "2"), (signal.SIGINT, "3")):
            os.kill(wrapper.pid, sig)
            _wait_text(got, n, wrapper)
        assert wrapper.poll() is None
        held = _status(env)
        assert held.returncode == 1 and held.stdout.startswith("HELD "), held.stdout + held.stderr
        second = _run(["--", *_py(f"open({str(intruder)!r},'w')")], env)
        assert second.returncode == 75, second.stderr
        assert not intruder.exists()
        release.write_text("go", encoding="utf-8")
        assert wrapper.wait(timeout=TIMEOUT) == 4
    finally:
        _kill_pid(_pid_or_none(marker))
        _kill_group(wrapper)
    assert got.read_text(encoding="utf-8") == "3"
    assert not intruder.exists()
    _assert_free(env)

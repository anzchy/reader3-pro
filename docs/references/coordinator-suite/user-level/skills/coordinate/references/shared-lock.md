# Shared-resource locks

Start by trying to eliminate the shared resource: give each unit its own port, temp directory or
data directory. Use a lock only when one resource really cannot be shared, such as CPU-bound E2E
runs whose flakes appear under contention.

## Preferred: an OS-released lock around the lane command

Wrap the lane command in a script that holds an `fcntl`/`flock` lock for the life of the run
(`<lock-wrapper> -- <lane command>`), and point the lane's configured command at the wrapper.

- **The kernel frees the lock when the process dies.** There is no release step, no break and no
  staleness to judge, so no peer can be left holding it and no permission can block a release.
- Every run of the lane holds the lock automatically, including the verifier's.
- Write an owner file (session, SHA, start time) for `status` only. The lock itself is the flock.
- **Fail fast.** If the lock is held, print `BUSY <owner>` and exit non-zero at once. Never wait
  inside the lane, because the wait counts against the lane's timeout. Callers wait outside
  through Monitor with an until-loop on `status`. Never use a foreground sleep.
- **No-op on CI** (for example when `GITHUB_ACTIONS` is set): CI runners do not share the resource.

```python
#!/usr/bin/env python3
# usage: <lock-wrapper> [status] | -- <lane command...>
import fcntl, os, subprocess, sys, time
L = os.environ.get("LOCK_FILE", os.path.expanduser("~/.cache/<project>-e2e.lock"))
if sys.argv[1:2] == ["status"]:
    with open(L, "a+") as f:
        try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: f.seek(0); print("HELD", f.read().strip()); sys.exit(1)
    print("FREE"); sys.exit(0)
cmd = sys.argv[sys.argv.index("--") + 1:]
if os.environ.get("GITHUB_ACTIONS"): sys.exit(subprocess.call(cmd))
f = open(L, "a+")
try: fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError: f.seek(0); print("BUSY", f.read().strip()); sys.exit(75)
f.seek(0); f.truncate(); f.write(f"{os.environ.get('SESSION','?')} {time.time():.0f}\n"); f.flush()
sys.exit(subprocess.call(cmd))  # lock released by the kernel when this process exits
```

## Fallback: mkdir plus owner file

Use only where an flock wrapper cannot run. It needs every rule below.

1. **Every participant must have a release path that works.** Keep acquire, release, status and
   break in one committed script, and pre-approve it once (`Bash(scripts/<lock> *)`). A raw
   `rm -rf` can be denied by one peer's permissions, and then everyone else stalls.
2. **Pre-flight every worktree at fan-out.** Each peer runs acquire and then release once, and
   reports the result in CP0.
3. **Record the owner:** session name, SHA, start time.
4. **Stale detection is mechanical.** The threshold is derived from the lane's configured timeout
   plus a margin, never hard-coded. If the lock is stale and a side-effect probe shows no running
   process, the next acquirer may `break` it and logs the break with the old owner's details. If
   staleness is ambiguous, escalate to the user.
5. **No laundering.** If a peer's release was *denied*, the coordinator must not run the same
   command for it. Escalate to the user and fix the allowlist. Breaking a *stale* lock under
   rule 4 is protocol, not laundering.
6. **Always release, even on failure.** Use `trap` in the script that wraps the lane.

Adding either script to a repo is implementation work. Put it through the project's normal gate
or TDD workflow on its own branch.

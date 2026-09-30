#!/bin/bash
# 归因臂：同一压力配方 + e2e_diag_dump 插件。红的那一刻把 window.Reader3NotesDiag.entries()
# dump 到 E2E_DIAG_OUT。冻结集零改动。
set -u
cd /Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro/.claude/worktrees/019-frozen-set-debts
BASE="$1"; MAX="${2:-5}"
mkdir -p "$BASE/logs" "$BASE/dumps"

N=$(sysctl -n hw.ncpu)
PIDS=""
for i in $(seq 1 "$N"); do ( while : ; do : ; done ) & PIDS="$PIDS $!"; done
trap 'kill $PIDS 2>/dev/null' EXIT
echo "压力进程 $N 个已起（归因臂）"

export E2E_DIAG_ALWAYS=1
RED=0
for r in $(seq 1 "$MAX"); do
  E2E_DIAG_OUT="$BASE/dumps/run-$r" PYTHONPATH=scripts \
  env -u FORCE_COLOR uv run pytest tests/e2e -m baseline_1b \
      --browser chromium -q -p no:cacheprovider -p e2e_diag_dump \
      > "$BASE/logs/run-$r.log" 2>&1
  rc=$?
  LOAD=$(uptime | sed 's/.*load averages*: //' | awk '{print $1}')
  SUM=$(grep -E "(passed|failed)" "$BASE/logs/run-$r.log" | tail -1)
  [ "$rc" -ne 0 ] && { MARK="🔴"; RED=$((RED+1)); } || MARK="🟢"
  echo "| $r | $MARK | $SUM | $LOAD |"
  grep -E "^FAILED" "$BASE/logs/run-$r.log" | sed 's/^/      /'
  grep -E "AssertionError" "$BASE/logs/run-$r.log" | sort -u | sed 's/^/      · /'
done
echo "=== 归因臂：$MAX 跑 $RED 红 ==="

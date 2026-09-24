#!/bin/bash
# 对照臂：完全照 2026-09-23 那次记录的配方，不带 tracing。
# 目的是判断「我这 7 跑全绿」是 tracing 引入的混杂，还是配方本身今天复现不出来。
# 纪律照台账：压力进程与 lane 同一个 shell 调用里起；load 在 lane 结束那一刻、杀压力之前读。
set -u
cd /Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro
LOGDIR="$1"; MAX="${2:-7}"
mkdir -p "$LOGDIR"

N=$(sysctl -n hw.ncpu)
PIDS=""
for i in $(seq 1 "$N"); do ( while : ; do : ; done ) & PIDS="$PIDS $!"; done
trap 'kill $PIDS 2>/dev/null' EXIT
echo "压力进程 $N 个已起（无 tracing 对照臂）"

RED=0
for r in $(seq 1 "$MAX"); do
  env -u FORCE_COLOR uv run pytest tests/e2e -m baseline_1b \
      --browser chromium -q -p no:cacheprovider > "$LOGDIR/run-$r.log" 2>&1
  rc=$?
  LOAD=$(uptime | sed 's/.*load averages*: //' | awk '{print $1}')
  SUM=$(grep -E "(passed|failed)" "$LOGDIR/run-$r.log" | tail -1)
  if [ "$rc" -ne 0 ]; then MARK="🔴"; RED=$((RED+1)); else MARK="🟢"; fi
  echo "| $r | $MARK | $SUM | $LOAD |"
  grep -E "^FAILED" "$LOGDIR/run-$r.log" | sed 's/^/      /'
done
echo "=== 无 tracing 对照臂：$MAX 跑 $RED 红 ==="

#!/bin/bash
# 压力下反复跑 baseline_1b，跑到第一次红就停，把 trace 留在 run-N 目录里。
# 归因靠的是 011 已证的不变式：写成功不往 Reader3NotesDiag 环里记任何东西。
# 于是 —— 环里有记录 ⇒ 产品缺陷；环是空的 ⇒ 客户端写成功了 ⇒ 是那 8 秒不够。
set -u
cd /Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro
BASE="$1"; MAX="${2:-6}"
mkdir -p "$BASE"

N=$(sysctl -n hw.ncpu)
PIDS=""
for i in $(seq 1 "$N"); do ( while : ; do : ; done ) & PIDS="$PIDS $!"; done
trap 'kill $PIDS 2>/dev/null' EXIT
echo "压力进程 $N 个已起"

for r in $(seq 1 "$MAX"); do
  OUT="$BASE/run-$r"
  echo "=== run $r / $MAX ===  $(uptime | sed 's/.*load/load/')"
  env -u FORCE_COLOR uv run pytest tests/e2e -m baseline_1b \
      --browser chromium -q -p no:cacheprovider \
      --tracing=retain-on-failure --output="$OUT" 2>&1 | tail -20
  rc=${PIPESTATUS[0]}
  echo "run $r rc=$rc"
  if [ "$rc" -ne 0 ]; then echo ">>> 红了，停在 run $r，trace 在 $OUT"; exit 0; fi
done
echo ">>> $MAX 跑全绿，没复现"

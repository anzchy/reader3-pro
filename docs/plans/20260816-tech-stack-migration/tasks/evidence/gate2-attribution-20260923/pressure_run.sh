#!/bin/bash
# 机制挑战闸第 2 项的归因跑：同一压力剖面 + Playwright tracing。
# tracing 把浏览器 console 收进 trace.zip，于是能读到 [Annotations] notes write failed，
# 而这不需要改冻结的 conftest.py。
# 用法：pressure_run.sh <输出目录>
set -u
cd /Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro

OUT="$1"
mkdir -p "$OUT"

N=$(sysctl -n hw.ncpu)
echo "ncpu=$N  输出=$OUT"

PIDS=""
for i in $(seq 1 "$N"); do
  ( while : ; do : ; done ) &
  PIDS="$PIDS $!"
done
trap 'kill $PIDS 2>/dev/null' EXIT

echo "--- load before ---"
uptime

env -u FORCE_COLOR uv run pytest tests/e2e -m baseline_1b \
    --browser chromium -q -p no:cacheprovider \
    --tracing=retain-on-failure --output="$OUT" 2>&1 | tail -30
echo "pytest rc=${PIPESTATUS[0]}"

echo "--- load after ---"
uptime

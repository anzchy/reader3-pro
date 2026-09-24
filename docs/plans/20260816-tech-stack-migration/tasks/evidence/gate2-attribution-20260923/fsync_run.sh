#!/bin/bash
set -u
T=/Users/jackcheng/.claude/jobs/9dae5fa1/tmp
cd /Users/jackcheng/Documents/01_Coding/Front-end-projects/reader3-pro

echo "=== 无压力对照 ==="
python3 "$T/fsync_probe.py" "$T" 12

N=$(sysctl -n hw.ncpu)
PIDS=""
for i in $(seq 1 "$N"); do ( while : ; do : ; done ) & PIDS="$PIDS $!"; done
trap 'kill $PIDS 2>/dev/null' EXIT
sleep 2
echo "=== 压力下（$N 个忙等）==="
uptime
python3 "$T/fsync_probe.py" "$T" 25
uptime

"""同一压力配方下，直接测 save_annotations 那套系统调用的延迟。
复刻 notes_service.save_annotations 的形状：mkstemp -> json.dump -> flush -> fsync -> replace。
不碰真实 books/，写到自己的临时目录。"""
import json, os, statistics, sys, tempfile, time

d = tempfile.mkdtemp(prefix="fsyncprobe.", dir=sys.argv[1])
target = os.path.join(d, "notes.json")
payload = {"schema_version": 1, "book_id": "smoke_data",
           "annotations": [{"id": f"a{i}", "quote": "x" * 80} for i in range(6)]}

lat = []
t_end = time.time() + float(sys.argv[2])
while time.time() < t_end:
    t0 = time.perf_counter()
    fd, tmp = tempfile.mkstemp(prefix=".notes.", suffix=".tmp", dir=d)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, target)
    lat.append((time.perf_counter() - t0) * 1000)

lat.sort()
def pct(p): return lat[min(len(lat) - 1, int(len(lat) * p / 100))]
print(f"n={len(lat)}  min={lat[0]:.2f}ms  p50={pct(50):.2f}ms  p90={pct(90):.2f}ms "
      f"p99={pct(99):.2f}ms  max={lat[-1]:.2f}ms")

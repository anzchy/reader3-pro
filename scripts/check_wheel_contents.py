#!/usr/bin/env python3
"""0.2 wheel 内容检查 —— 打出来的 wheel 必须能真的把阅读器跑起来。

定义处：`docs/plans/20260816-tech-stack-migration/tasks/007-hygiene-and-contracts.md` 步骤 0.2。

**这个 bug 在开发中永远看不见。** `uv run` 走源码树，模板与静态资源都在原地；
只有 `pip install` 一个 wheel 之后才会暴露。原 `package-data` 写的是 `static/*`，
而 setuptools 的 `*` **不递归**——`static/js/`、`static/css/`、`static/vendor/`
三个子目录一个都没打进去，装出来的阅读器白屏（`annotations.css`、`annotations.js`、
`epub.min.js` 全缺），而 `uv build` 本身是成功的、不报任何警告。

判定不是「抽查几个文件在不在」，是**逐文件对账**：源码树 `web/templates/` 与
`web/static/` 下的每一个文件都必须在 wheel 里有对应条目。抽查会在有人新增
`static/img/` 时静默失效，对账不会。

用法：`python3 scripts/check_wheel_contents.py [--root <repo>]`（自己调 `uv build`，约 10 秒）

**013 WI-9 A9.5：`static/dist/` 至少要有一个成员进 wheel。** Vite 产物提交在
`static/dist/`（任意深度）。逐文件对账只证明「树里有的都进了 wheel」——树里一个 dist
文件都没有时（被 gitignore 掉、被删、构建没跑），对账是空真，照样绿。所以另判一条：
wheel 里 `static/dist/` 下的成员数必须 ≥ 1，否则退出码 1。

`--root` 让测试把它指向 tmp 里的一份树拷贝（C9.05 / C9.42 往那里种探针、改
pyproject），真仓库不被弄脏。不给时就是本仓库根。
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "src" / "reader3_app"
# 打包时该被带上的目录，相对 src/。别在这里列文件名——列目录，逐文件对账。
ASSET_DIRS = ["reader3_app/web/templates", "reader3_app/web/static"]
# 这三个是 0.2 的原始症状。单独点名是为了让失败信息直接指向病因，
# 而不是让人从一串路径里自己看出「哦，子目录整个没了」。
# css/ 那一个原本点名的是个死样式文件，013 WI-9（§9.2）删死文件时换成同目录的
# 活文件 annotations.css（reader.html 加载它）——金丝雀必须指向会一直在的文件。
CANARIES = [
    "reader3_app/web/static/js/annotations.js",
    "reader3_app/web/static/css/annotations.css",
    "reader3_app/web/static/vendor/epub.min.js",
]
IGNORE = {".DS_Store"}
#: 013 WI-9：Vite 产物目录（wheel 内路径）。见模块 docstring。
DIST_PREFIX = "reader3_app/web/static/dist/"


def _set_root(root: Path) -> None:
    global ROOT, PKG
    ROOT = root.resolve()
    PKG = ROOT / "src" / "reader3_app"


def expected_files() -> set[str]:
    out: set[str] = set()
    for rel in ASSET_DIRS:
        base = ROOT / "src" / rel
        if not base.is_dir():
            print(f"✗ 源码树里没有 {rel}/ —— 是不是挪走了？", file=sys.stderr)
            raise SystemExit(2)
        for f in base.rglob("*"):
            if not f.is_file() or f.name in IGNORE:
                continue
            if "__pycache__" in f.parts:
                continue
            out.add(str(f.relative_to(ROOT / "src")))
    return out


def build_wheel(outdir: Path) -> Path:
    # 必须先清掉两处构建残留，否则这个检查会给出**假绿**。
    #
    # 1. `build/lib/` —— setuptools 先把文件拷到这里再打包，且不会删掉上一次
    #    留下的、这次已经不该带的文件。
    # 2. `src/*.egg-info/SOURCES.txt` —— 这条更隐蔽。`pyproject.toml` 开了
    #    `include-package-data = true`，于是 setuptools 会把 SOURCES.txt 里
    #    列的文件一并算作包数据；而 SOURCES.txt 是上一次构建生成的、列全了
    #    整棵树。结果是：**只要本地做过一次成功构建，把 package-data 改回坏的
    #    `static/*` 之后 wheel 依然是完整的**，检查照样绿。已实测确认。
    #
    # CI 是干净检出，两处残留都不存在，所以这个陷阱只在本地咬人——而本地
    # 恰恰是改 pyproject.toml 的人第一时间验证的地方。两处都是 gitignore
    # 的构建产物，删掉下次构建自己会重建。
    for stale in [ROOT / "build", *(ROOT / "src").glob("*.egg-info")]:
        if stale.is_dir():
            shutil.rmtree(stale)

    proc = subprocess.run(
        ["uv", "build", "--wheel", "-o", str(outdir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print("✗ uv build 失败：", file=sys.stderr)
        print(proc.stdout[-2000:], file=sys.stderr)
        print(proc.stderr[-2000:], file=sys.stderr)
        raise SystemExit(2)
    wheels = sorted(outdir.glob("*.whl"))
    if len(wheels) != 1:
        print(f"✗ 期望正好一个 .whl，实际 {len(wheels)} 个", file=sys.stderr)
        raise SystemExit(2)
    return wheels[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None, help="仓库根（默认：本脚本所在仓库）")
    args = parser.parse_args(argv)
    if args.root is not None:
        _set_root(args.root)

    want = expected_files()
    with tempfile.TemporaryDirectory() as td:
        wheel = build_wheel(Path(td))
        with zipfile.ZipFile(wheel) as z:
            have = set(z.namelist())
        name = wheel.name

    missing = sorted(want - have)
    dist_members = sorted(n for n in have if n.startswith(DIST_PREFIX) and not n.endswith("/"))
    absent_canaries = [c for c in CANARIES if c not in have]

    if absent_canaries:
        print("✗ wheel 里缺了阅读器跑起来必需的文件：", file=sys.stderr)
        for c in absent_canaries:
            print(f"    {c}", file=sys.stderr)
        print(
            "\n  多半是 pyproject.toml 的 [tool.setuptools.package-data] 又被改回了\n"
            "  非递归的 `static/*`。setuptools 的 `*` 不进子目录，要写 `static/**/*`。",
            file=sys.stderr,
        )
    if missing:
        print(f"\n✗ 逐文件对账：源码树里有 {len(missing)} 个资源没进 wheel：", file=sys.stderr)
        for m in missing[:30]:
            print(f"    {m}", file=sys.stderr)
        if len(missing) > 30:
            print(f"    …… 另有 {len(missing) - 30} 个", file=sys.stderr)

    if not dist_members:
        print(
            f"\n✗ wheel 里 static/dist/ 下 0 个文件（{DIST_PREFIX}）。Vite 产物没进 wheel：\n"
            "  要么源码树里就没有 dist/（没构建？被 .gitignore 吞了？），要么 package-data\n"
            "  把它排除了。阅读器的 TS 入口全在这里，缺了它页面起不来。",
            file=sys.stderr,
        )

    if missing or absent_canaries or not dist_members:
        return 1

    print(
        f"\n0.2 wheel 内容检查：{name} 打包了 {len(want)} 个模板与静态资源，"
        f"三个子目录（js / css / vendor）齐全，缺 0。"
    )
    print(f"static/dist/ 进 wheel 的文件数：{len(dist_members)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

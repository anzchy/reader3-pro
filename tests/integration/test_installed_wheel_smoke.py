"""把 `scripts/smoke_installed_wheel.py` 接进 pytest，让它有个日常的运行节奏。

**为什么需要这个文件。** 那条守卫本身早就写好了（`1392b1f`），但它只挂在
`.github/workflows/lint.yml` 的 `wheel` job 上。2026-08-23 CI 改成仅发版触发之后，
它就退化成了「发版那天才会说话」——而它守的恰恰是全仓库唯一一个
**只有干净环境才看得见** 的故障类别（依赖出大版本 → 装出来每个页面 500）。
发版当天才发现这种问题，等于没有守卫。

**为什么单独一个 lane，不进 unit。** 它要 `uv build` ＋ 建 venv ＋ 装包 ＋ 起真
服务，几十秒起步。unit lane 挂在 `taskCompleted` 和 `commit` 上，2 秒跑完是它
能一直被人容忍的前提；往里塞一个分钟级的检查，结果不是「大家等一分钟」，
是「大家开始用 --no-verify」。所以它落在 `tests/integration/`，由
`.claude/tdd-guardian/config.json` 的 `packaging` lane 在 push 时跑。

三档节奏因此是：每次提交 → unit（2s）；每次 push → packaging（分钟级）；
每次发版 → CI 里再跑一遍（同一个脚本，环境更干净）。

**为什么是薄薄一层包装。** 真正的断言全在脚本里——它起真进程、打四个路由、
比对状态码与正文。这里不重复那些判断，也不为了「测试里要有断言」把脚本拆开：
本文件解决的是**运行节奏**，不是断言覆盖。脚本改判据时，这里不需要跟着改。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "smoke_installed_wheel.py"


def _load_script():
    """按路径加载 scripts/ 下的脚本——那个目录不是包，import 不到。"""
    spec = importlib.util.spec_from_file_location("smoke_installed_wheel", SCRIPT)
    assert spec and spec.loader, f"加载不了 {SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_exists() -> None:
    """守卫脚本本身不许消失。

    这条是免费的、毫秒级的，跟 slow 那条分开：如果哪天有人删了或改名了
    `smoke_installed_wheel.py`，unit lane 之外的人也该立刻知道，而不是等到
    某次 push 跑 packaging lane 时才看见一个 import 错误。
    """
    assert SCRIPT.is_file(), f"守卫脚本不见了：{SCRIPT}"


@pytest.mark.slow
def test_installed_wheel_serves_all_routes() -> None:
    """打 wheel → 装进干净 venv（依赖按最新版解析）→ 起真服务 → 四个路由不许 5xx。

    判据与退出码都由脚本定义；这里只把非 0 翻译成测试失败。脚本失败时会把
    失败的路由、正文前 200 字与服务端输出尾部打到 stderr，pytest 会原样带出来。
    """
    smoke = _load_script()
    try:
        rc = smoke.main()
    except SystemExit as e:  # 脚本在构建/装包失败时走这条路，不是路由问题
        pytest.fail(f"smoke_installed_wheel.py 在起服务之前就退出了（SystemExit {e.code}）")
    assert rc == 0, f"装出来的 wheel 有路由起不来或渲染不了（脚本退出码 {rc}，详见上方 stderr）"

"""前端产物会去打的**外部域**，必须是一张有限的、显式登记的清单。

**为什么有这条用例：一次真实的整套挂掉。** 2026-09-03，`tests/e2e` 从 21 passed / 32s
变成 16 failed / 545s。根因不在改动里，而在 `reader.html` 与 `library.html` 的 `<head>`：
两份模板各有一组指向 `fonts.googleapis.com` 的**阻塞式** `<link rel="stylesheet">`。
那台机器上 chromium 够不到这个域，请求挂满 30 秒，于是整页的 `load` 事件永不到达，
每条要开页面的用例各赔 30 秒（16 × 30s ≈ 545s，与实测吻合）。

`tests/e2e/conftest.py` 的 `context` fixture 已经把浏览器出网掐掉，所以 e2e 不会再因为
外网而红。**但那是止血，不是登记。**掐掉之后，往模板里新加一个 CDN 依赖不会让任何东西
变红——它只是被静静地 abort 掉，页面少了个资源，而没人会知道多了一条出网依赖。这正是
§0 第六条纪律说的「静默失效的规则必须机器可查」。这条用例就是那个机器检查，且它落在
**unit 道**（`gateOn: commit`）而不是 e2e 道（`gateOn: push`），所以在 commit 关就响。

**断言写成相等而不是包含关系**，两个方向都要红：

* 多出一个域 → 红。有人加了新的 CDN 依赖，得先在这里登记，顺带被迫想一下离线场景。
* 少一个域 → 也红。等跨波欠账 #5（自托管字体）兑付时，删掉模板里的 `<link>` 必须同时
  删掉这里的登记；否则清单会烂成一张「曾经用过什么」的考古记录。

**期望清单是写死的字面量，不从被扫文件里推导**（§0 第五条纪律）。从产物里读出期望值再
拿去和产物比，是个恒真式：模板加十个 CDN 它也照样绿。

**扫描面为什么含 `static/`。** `js/epub-renderer.js` 往 epub.js 的 iframe 里**再注一次**
同一个字体 URL。只扫模板会漏掉它——而 iframe 里的那次请求同样会拖住渲染。
`static/vendor/` 排除在外：那是第三方 vendored 产物，不是本仓库的设计决定。

**为什么不区分 `<a href>` 与子资源。** 严格说只有子资源（`<link>` / `<script src>` /
`<img src>` / CSS `url()`）才会在加载时发请求，`<a href>` 不会。区分它们要真的解析 HTML，
而解析错了的失效方式是**静默漏报**——把一个真的子资源误判成链接，这条用例就白立了。
在「偶尔要为一个无害的外链多写一行登记」和「可能悄悄漏掉一个真依赖」之间，选前者。
今天两份模板里一个外链都没有，这个成本是零。

**可失败性证据（§0 第四条纪律）。** 本条是特征化用例——被测的两份模板和 `epub-renderer.js`
早已存在，红根本不可得，所以下面这两次是**定向破坏 → 记录失败输出 → 还原核验**，
每次只动一个判据：

| 破坏点 | 失败输出（逐字） |
|---|---|
| `reader.html` 的 `<head>` 里插一行 `<script src="https://cdn.jsdelivr.net/npm/x.js">` | `前端产物新增了未登记的出网依赖：['cdn.jsdelivr.net']` ／ `  cdn.jsdelivr.net ← ['src/reader3_app/web/templates/reader.html']` |
| `EXPECTED_EXTERNAL_HOSTS` 里塞一个 `"cdn.dead.example"` | `EXPECTED_EXTERNAL_HOSTS 里这些域已经没人用了：['cdn.dead.example']` |

两次都逐字还原（`git diff --stat` 无输出），还原后 2 passed。第一条的失败信息里带着
**是哪个文件**，这不是装饰：出网依赖可能被加在模板、也可能被加在 `static/` 下的某个 js 里
（`epub-renderer.js` 就是后者），只报域名会让人先去翻错的文件。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Set

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATES = REPO_ROOT / "src" / "reader3_app" / "web" / "templates"
STATIC = REPO_ROOT / "src" / "reader3_app" / "web" / "static"

#: 被扫的产物。`static/vendor/` 由 `_iter_files` 排除。
SCAN_GLOBS = (
    (TEMPLATES, "*.html"),
    (STATIC, "**/*.js"),
    (STATIC, "**/*.css"),
)

#: 允许出现的外部域——**每一个都是一条已知的出网依赖**，不是「见过的域名」。
#:
#: 这两个是 Google Fonts 的 CSS 与字体文件宿主，出现在两份模板的 `<head>` 与
#: `js/epub-renderer.js` 注入 iframe 的那段里。它们的存在是**已知代价、显式推迟**：
#: 见 009 任务书 §0.6 跨波欠账 #5（一个本地自托管的离线阅读器不该在首屏依赖外网字体）。
#: 兑付那条欠账时，这里要跟着删干净。
EXPECTED_EXTERNAL_HOSTS = frozenset({"fonts.googleapis.com", "fonts.gstatic.com"})

#: XML/SVG 命名空间。它长得像 URL，但浏览器**从不去取它**——它只是个标识符字符串。
#: 把它算进出网依赖会让这条用例永远红在一个假问题上。
NAMESPACE_HOSTS = frozenset({"www.w3.org"})

_URL_RE = re.compile(r"https?://([^/\"'\s)>]+)")


def _hosts_in_text(text: str) -> Set[str]:
    """一段文本里出现的外部主机名（已剔除命名空间宿主）。端口保留在主机名里。"""
    return {h for h in _URL_RE.findall(text) if h.split(":")[0] not in NAMESPACE_HOSTS}


def _iter_files():
    for root, pattern in SCAN_GLOBS:
        for path in sorted(root.glob(pattern)):
            if "vendor" in path.relative_to(REPO_ROOT).parts:
                continue
            yield path


def _scan() -> Dict[str, Set[str]]:
    """主机名 → 出现在哪些文件（仓库相对路径）。给失败信息用，让它指对地方。"""
    found: Dict[str, Set[str]] = {}
    for path in _iter_files():
        rel = str(path.relative_to(REPO_ROOT))
        for host in _hosts_in_text(path.read_text(encoding="utf-8")):
            found.setdefault(host, set()).add(rel)
    return found


def test_every_external_host_in_frontend_assets_is_registered() -> None:
    found = _scan()
    actual = set(found)

    unregistered = actual - EXPECTED_EXTERNAL_HOSTS
    assert not unregistered, (
        f"前端产物新增了未登记的出网依赖：{sorted(unregistered)}\n"
        + "".join(f"  {h} ← {sorted(found[h])}\n" for h in sorted(unregistered))
        + "浏览器在加载页面时会真的去打这些域。加载不到时，阻塞式的那类（<link "
        "rel=stylesheet>、<script src>）会把整页的 load 事件拖到超时——2026-09-03 "
        "就是这样让 tests/e2e 从 32s 变成 545s 的。\n"
        "要么把它改成本地资源，要么在本文件的 EXPECTED_EXTERNAL_HOSTS 里登记并写明"
        "离线场景下的降级行为。"
    )

    stale = EXPECTED_EXTERNAL_HOSTS - actual
    assert not stale, (
        f"EXPECTED_EXTERNAL_HOSTS 里这些域已经没人用了：{sorted(stale)}\n"
        "清单要跟着产物走，否则会烂成一张「曾经用过什么」的考古记录。"
        "（若这是在兑付 009 §0.6 欠账 #5，删掉对应条目即可。）"
    )


def test_the_check_itself_can_fail() -> None:
    """这条检查漏写不会红，所以它自己必须被检查（§0 第六条纪律）。"""
    # 真的子资源：认得出来。
    assert _hosts_in_text('<link href="https://cdn.example.com/a.css">') == {"cdn.example.com"}
    # 带端口：端口留在主机名里，因为 `example.com:8443` 和 `example.com` 是两条不同的出网路径。
    assert _hosts_in_text('<script src="http://example.com:8443/x.js">') == {"example.com:8443"}
    # SVG 命名空间：不算出网。带端口的 w3c 写法也一样剔除。
    assert _hosts_in_text('<svg xmlns="http://www.w3.org/2000/svg">') == set()
    # 相对路径：本来就不出网。
    assert _hosts_in_text('<link href="/static/css/app.css">') == set()
    # 一段文本里的多个域全都要拿到，不能只拿第一个。
    assert _hosts_in_text('a https://one.example b https://two.example') == {
        "one.example",
        "two.example",
    }

"""WI-16 · 桩契约：gate 一直不放行时，ollama 形桩的响应体**干净终止**且不含末块。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` §WI-16「【R2 新增】桩契约」一条，
lane = **unit**。任务书：`docs/plans/20260816-tech-stack-migration/tasks/009-e2e-annotations.md`
§6 X-1 行。

**被测的就是桩本身，桩在这里不是替身，是主角。** `tests/fixtures/ai_stub.py` 是 X-1a′ / X-1c
（e2e lane）赖以成立的测试基础设施：那两条用例让桩在末块之前阻塞于 `gate.wait(STUB_GATE_TIMEOUT)`，
并以「桩记录 gate 是被 `set()` 放行的」作为「浏览器先渲染出了首块」的直接证据。这条因果链有一个
隐藏前提——**gate 超时后桩必须干净收尾，绝不中止连接**：

* 干净收尾（chunked 编码正常写出 `0\\r\\n\\r\\n` 终止块、无末块、无 `done` 行）⇒ `server.py` 的
  `worker_ollama` 读到 EOF 落出循环、推 `{"type":"done"}` ⇒ `ai.js` 保留已渲染的部分答案 ⇒
  X-1a′ 以 **`assert stub.completed is True` 失败**（可诊断）。
* 中止连接（`self.wfile.close()` / `raise` / 半路关 socket）⇒ `urllib` 在 worker 内抛
  `IncompleteRead` ⇒ 推 `{"type":"error"}` ⇒ `ai.js` 用 `Error: …` **覆写**那条消息 ⇒ X-1a′ 的
  `wait_for_function` 条件永远不满足 ⇒ 以 **timeout 失败**，与「环境慢」不可区分，会被当 flaky
  隔离掉——而隔离一条 `baseline_1b` 用例会扣掉 soak 计数，所以隔离的压力是真实存在的。

**成本说明**：本条的存在理由是把一条 e2e 用例的诊断性买下来，代价是毫秒（只起桩自己的 HTTP
server + 一次 `requests` 调用；不起浏览器、不起 `live_server`、不碰 `ai_settings`）。X-1a′ 一次
失败若表现为 timeout，人要花的时间以小时计，而最省事的结论（「flaky，隔离掉」）恰好销毁的是全表
唯一能区分「流式」与「读完再演」的那条用例。

四条断言（矩阵 Expected output 逐条对应）：
  1. 响应体逐行 `json.loads` 后取 `["message"]["content"]`，列表 **== `DELTAS[:3]`**（三行，等值）；
  2. 没有任何一行含 `"done": true`；
  3. 读取过程不抛任何连接异常（`ChunkedEncodingError` / `ConnectionError` / 不完整 chunked 结尾）；
  4. `stub.completed is False` 且 `stub.gate_released_by_render is False`。

自检（矩阵）：把桩的超时分支改成中止连接 ⇒ (3) 红；改成「超时后照发末块」⇒ (1)(2)(4) 红。
`return expectedValue` 式实现无处可返：断言落在真实 HTTP 响应体的字节上。
"""

from __future__ import annotations

import json
from typing import Iterator, List

import pytest
import requests

from ai_stub import (  # type: ignore[import-not-found]
    CASE_TIMEOUT_S,
    DELTAS,
    RENDER_WAIT_TIMEOUT_S,
    STUB_GATE_TIMEOUT,
    OllamaStub,
)

# 三个常量的序关系是 X-1a′ 失败形态的全部保证，桩模块里已有一句模块级 assert；这里再断一次是
# 为了让「有人把 assert 从桩模块里删掉」这件事在 unit lane 就响，而不是等到 e2e 一条神秘超时。
assert STUB_GATE_TIMEOUT < RENDER_WAIT_TIMEOUT_S < CASE_TIMEOUT_S

# 本条只需要 gate 超时**发生**；5.0s 的默认值是 e2e 一侧为 X-1a′ 定的，unit lane 不必陪着等满。
# 用一个更短的超时只改「等多久」，不改「超时后怎么收尾」——后者才是被测的契约。
SHORT_GATE_TIMEOUT_S = 0.5

#: 「零真实出网」的下半条：桩只许在回环上监听。写成常量是为了让下面两处引用同一个字面量。
LOOPBACK = "127.0.0.1"


@pytest.fixture
def gated_stub() -> Iterator[OllamaStub]:
    with OllamaStub(gate_timeout_s=SHORT_GATE_TIMEOUT_S) as stub:
        stub.gate_mode = True
        yield stub


def _read_ndjson_lines(resp: requests.Response) -> List[dict]:
    """逐行读完 chunked 响应体。`iter_lines` 在 chunked 结尾不完整时抛 `ChunkedEncodingError`。"""
    out: List[dict] = []
    for raw in resp.iter_lines(decode_unicode=False):
        if not raw:
            continue
        out.append(json.loads(raw.decode("utf-8")))
    return out


def test_the_stub_listens_on_the_loopback_interface_only(gated_stub: OllamaStub) -> None:
    """「零真实出网」的下半条：判据是 socket **实际绑定**的地址，不是拼出来的字符串。

    2026-09-05 审计（MEDIUM）：原来的判据是 `stub.base_url.startswith("http://127.0.0.1:")`，
    而 `base_url` 返回的是 `f"http://{_HOST}:{port}"`、bind 用的也是同一个 `_HOST`。同一个
    常量既当被测对象又当参照物：把 `_HOST` 改掉两边一起变（那样确实会红），但**在 bind 那行
    写一个与 `_HOST` 不同的字面量**（`ThreadingHTTPServer(("0.0.0.0", 0), …)`）——桩就监听在
    所有网卡上了，而 `base_url` 仍然一字不差地说自己在 127.0.0.1，原断言全绿。

    所以这里问的是运行中的 server 自己：`server_address[0]`。两条断言各管一头——
    第一条管「绑对了没有」，第二条管「说的和绑的是不是同一个地方」（`base_url` 是写进
    沙箱 `ai_settings.json` 的那个值，被测服务照它去连；两者不一致时桩会收不到请求，
    而失败形态是一次不知所云的 provider 报错）。
    """
    stub = gated_stub
    assert stub.bound_host == LOOPBACK, (
        f"桩实际绑定在 {stub.bound_host!r}，不是 {LOOPBACK!r}——它在回环以外的网卡上可达了"
    )
    assert stub.base_url == f"http://{LOOPBACK}:{stub.port}", (
        f"桩对外宣告的 base_url（{stub.base_url!r}）与它实际绑定的 "
        f"{stub.bound_host}:{stub.port} 不是同一个地址"
    )


# 真的对 tests/fixtures/ai_stub.py 起的那个回环 HTTP stub 发请求（requests）。
# ai_stub.py 在 8 条冻结 suite_hash 路径里，改不了；豁免标记是唯一的杠杆。
# 名单锁在 tests/unit/test_egress_backstop_unit.py 的 EXPECTED_EXEMPTIONS。
@pytest.mark.real_loopback_socket
def test_gate_timeout_ends_the_body_cleanly_without_the_last_delta(gated_stub: OllamaStub) -> None:
    stub = gated_stub
    assert stub.bound_host == LOOPBACK, f"桩必须只在回环地址上监听：{stub.bound_host}"

    # 全程不调用 gate.set()。
    with requests.post(
        f"{stub.base_url}/api/chat",
        json={"model": "stub", "messages": [{"role": "user", "content": "Alpha"}], "stream": True},
        stream=True,
        timeout=STUB_GATE_TIMEOUT + 5.0,
    ) as resp:
        assert resp.status_code == 200, f"桩对 /api/chat 应答 {resp.status_code}，期望 200"
        assert resp.headers.get("Transfer-Encoding", "").lower() == "chunked", (
            "桩必须用 chunked 编码：只有带终止块的编码能让「干净终止」与「连接被拆」在客户端可区分。"
            f" 实际响应头：{dict(resp.headers)}"
        )
        # (3) 读取过程不抛任何连接异常 —— 抛了就是本条要防的那种「用中止连接表达不发末块」。
        try:
            lines = _read_ndjson_lines(resp)
        except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError) as e:
            pytest.fail(
                f"gate 超时后桩没有干净收尾，客户端读到连接异常：{type(e).__name__}: {e}。"
                " 这会让 X-1a′ 从「断言失败」退化成「timeout 失败」。"
            )

    # (1) 恰好 DELTAS[:3] 三行，逐行 content 列表等值。
    contents = [str((ln.get("message") or {}).get("content", "")) for ln in lines if "message" in ln]
    assert contents == list(DELTAS[:3]), (
        f"gate 未放行时桩应恰好发出前三块 {list(DELTAS[:3])!r}，实际 {contents!r}（共 {len(lines)} 行：{lines!r}）"
    )
    # (2) 没有 done 行。
    done_lines = [ln for ln in lines if ln.get("done") is True]
    assert done_lines == [], f"gate 未放行时不得发出 done 行，实际发了：{done_lines!r}"
    # (4) 桩侧标志位保持 False。
    assert stub.completed is False, "gate 未放行，completed 却为 True：末块被补发了（那会让 X-1a′ 恒绿）"
    assert stub.gate_released_by_render is False, "gate 从未被 set()，gate_released_by_render 却为 True"
    assert stub.gate_timed_out is True, "桩没有记录「gate 超时」——X-1c 依赖这个标志判断 stop 是否早于桩放弃"
    assert stub.request_count == 1, f"本条只发了一次请求，桩记到 {stub.request_count} 次"


# 真的对 tests/fixtures/ai_stub.py 起的那个回环 HTTP stub 发请求（requests）。
# ai_stub.py 在 8 条冻结 suite_hash 路径里，改不了；豁免标记是唯一的杠杆。
# 名单锁在 tests/unit/test_egress_backstop_unit.py 的 EXPECTED_EXEMPTIONS。
@pytest.mark.real_loopback_socket
def test_gate_released_before_timeout_sends_the_last_delta_and_done(gated_stub: OllamaStub) -> None:
    """对照支：gate 被 `set()` 放行时四块齐全且以 done 行收尾。

    没有这一条，上一条的 (1)(2) 对「桩压根从不发末块」的实现也绿——那样的桩会让 X-1b 恒红、
    X-1a′ 的 `completed` 永远 False，本条把「gate 放行 ⇒ 末块 + done」钉成桩的另一半契约。
    """
    stub = gated_stub
    stub.gate.set()  # 先放行再请求：桩的 wait 立即返回 True，走「被放行」分支。
    with requests.post(
        f"{stub.base_url}/api/chat",
        json={"model": "stub", "messages": [], "stream": True},
        stream=True,
        timeout=STUB_GATE_TIMEOUT + 5.0,
    ) as resp:
        assert resp.status_code == 200
        lines = _read_ndjson_lines(resp)

    contents = [str((ln.get("message") or {}).get("content", "")) for ln in lines if "message" in ln]
    assert contents == list(DELTAS), f"放行后应发出全部 {list(DELTAS)!r}，实际 {contents!r}"
    assert lines[-1].get("done") is True and lines[-1].get("done_reason") == "stop", (
        f"末行应为 {{'done': true, 'done_reason': 'stop'}}，实际 {lines[-1]!r}"
    )
    assert stub.completed is True
    assert stub.gate_released_by_render is True
    assert stub.gate_timed_out is False


# 真的对 tests/fixtures/ai_stub.py 起的那个回环 HTTP stub 发请求（requests）。
# ai_stub.py 在 8 条冻结 suite_hash 路径里，改不了；豁免标记是唯一的杠杆。
# 名单锁在 tests/unit/test_egress_backstop_unit.py 的 EXPECTED_EXEMPTIONS。
@pytest.mark.real_loopback_socket
def test_paths_other_than_api_chat_are_rejected_with_404(gated_stub: OllamaStub) -> None:
    """桩只认 `POST /api/chat`。任何别的路径 404：这是在钉「零真实出网」的另一面——
    被测服务若打了桩以外的端点（例如 `/api/version` 探活）也不会被桩静默成功。"""
    stub = gated_stub
    r = requests.get(f"{stub.base_url}/api/version", timeout=5)
    assert r.status_code == 404, f"GET /api/version 应 404，实际 {r.status_code}"
    r = requests.post(f"{stub.base_url}/v1/chat/completions", json={}, timeout=5)
    assert r.status_code == 404, f"openai 形状的路径应 404，实际 {r.status_code}"
    assert stub.request_count == 0, "404 的路径不该计入 request_count（它只数 /api/chat）"

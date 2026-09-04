"""进程内的 **ollama 形** provider 桩（009 WI-16 · X-1 AI SSE 流式）。

矩阵：`.claude/tdd-guardian/tests-20260901-224500.md` §WI-16 与文末 §A。

**为什么是 ollama 形状，不是 openai 形状。** `server.py` 的 `event_gen` 里只有 `worker_ollama`
逐块推送（逐行读 NDJSON、每行推一个 `chunk` 事件）；所有其他 provider 走 `worker_non_stream`，
把整段回答作为**单个** `chunk` 事件推出。用 openai 形状的桩，浏览器侧 DOM 更新次数恒为 1，
X-1a「增量渲染」不可能绿——那不是实现有问题，是用例选错了 provider。附带收益：`ollama` 不在
`_provider_requires_api_key` 的集合里，沙箱 settings 不必编一个假 key；`_ollama_root_base_url`
会削掉结尾的 `/v1`，所以 `base_url` 直接写 `http://127.0.0.1:{port}`。

**协议形状**（与 `worker_ollama` 的读法逐项对应）：`POST /api/chat` → 200，`Transfer-Encoding:
chunked`，NDJSON 行流，每行 `{"model": …, "message": {"content": "<delta>"}, "done": false}`，
末行 `{"done": true, "done_reason": "stop"}`；每行写完 `flush()`。其他路径一律 404。

**握手（gate 模式，X-1a′ / X-1c 用）**：`gate_mode=True` 时，桩写出 `DELTAS[:-1]` 后、写末块之前
阻塞于 `gate.wait(gate_timeout_s)`：
  * 被 `gate.set()` 放行 ⇒ 写末块 + done 行，`completed = True`、`gate_released_by_render = True`；
  * 超时 ⇒ **干净收尾**：照常写出 chunked 终止块 `0\\r\\n\\r\\n`，不写末块、不写 done 行，
    两个标志保持 False。**绝不中止连接**——那会让 `urllib` 在 `worker_ollama` 里抛异常、SSE 推
    `error`、`ai.js` 用 `Error: …` 覆写消息，X-1a′ 于是从「断言失败」退化成「timeout 失败」。
    这条契约由 `tests/unit/test_ai_stub_contract.py` 钉住。

**三个超时的序关系**是 X-1a′ 失败形态的全部保证，写成常量 + 一句模块级 `assert`，不写成注释：
序被打破时（例如有人把 gate 超时调到 20s「让 CI 宽松点」）红的是这句 assert，而不是某条 e2e
用例的神秘超时。

本模块**不 import playwright**：unit lane 与 e2e lane 都要能 import 它。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple

#: 桩按序发出的四个 delta。X-1a 的最终文本 == `"".join(DELTAS)`；首块含语料里真实出现的 `Alpha`
#: 只是为了让人读起来像一句回答——检索命中与否由**提问**里的关键词决定，不由回答决定。
DELTAS: Tuple[str, ...] = ("Alpha ", "是第一章的", "第一个", "词。")

#: 桩在末块前最多阻塞多久（gate 模式）。到点则干净收尾。
STUB_GATE_TIMEOUT = 5.0
#: 用例等「首个增量出现在 DOM」最多等多久（X-1a′ 步骤 3 的 `wait_for_function` 必须显式传它）。
RENDER_WAIT_TIMEOUT_S = 15.0
#: 整条用例的预算（本仓库未装 pytest-timeout；由 e2e 侧 fixture 把它设成 Playwright 的默认超时，
#: 并且用例里每一次等待都显式传更小的超时，见 `test_other_ai_streaming.py`）。
CASE_TIMEOUT_S = 30.0

# 「攒够一次性吐」的实现下：桩在 STUB_GATE_TIMEOUT 时干净收尾并保持 completed=False，
# 浏览器随后才一次性渲染；RENDER_WAIT 在那之后仍有余量等到渲染，于是用例走到
# `assert stub.completed is True` 并以**断言**失败——而不是先撞 RENDER_WAIT / CASE 超时。
assert STUB_GATE_TIMEOUT < RENDER_WAIT_TIMEOUT_S < CASE_TIMEOUT_S

_HOST = "127.0.0.1"
_CHAT_PATH = "/api/chat"


class _Handler(BaseHTTPRequestHandler):
    """每个连接一个实例；所有可变状态都在 `self.server.stub` 上。"""

    protocol_version = "HTTP/1.1"

    # 静音：默认把每个请求打到 stderr，e2e 的 pytest 输出里不需要这些。
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - 基类签名
        return

    def _write_chunk(self, payload: bytes) -> None:
        self.wfile.write(f"{len(payload):x}\r\n".encode("ascii") + payload + b"\r\n")
        self.wfile.flush()

    def _write_line(self, obj: Dict[str, Any]) -> None:
        self._write_chunk((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))

    def _end_chunked(self) -> None:
        # chunked 编码的终止块：有它，客户端才知道这是「正常结束」而不是「连接被拆」。
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def _reject(self, status: int = 404) -> None:
        body = json.dumps({"error": f"stub only serves POST {_CHAT_PATH}"}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def do_GET(self) -> None:  # noqa: N802 - 基类命名
        self._reject()

    def do_POST(self) -> None:  # noqa: N802 - 基类命名
        stub: OllamaStub = self.server.stub  # type: ignore[attr-defined]
        if self.path.split("?", 1)[0] != _CHAT_PATH:
            # 先把请求体读掉再拒绝，免得对端在写 body 时撞上 RST。
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            self._reject()
            return

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            payload = {"_unparsed": raw.decode("utf-8", errors="replace")}
        with stub._lock:
            stub.request_count += 1
            stub.payloads.append(payload)
        model = str((payload or {}).get("model") or "stub")

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Connection", "close")
        self.end_headers()

        deltas = list(stub.deltas)
        head, last = deltas[:-1], deltas[-1]
        for delta in head:
            self._write_line({"model": model, "message": {"role": "assistant", "content": delta}, "done": False})

        if stub.gate_mode:
            released = stub.gate.wait(stub.gate_timeout_s)
            if not released:
                # 超时：干净收尾，不写末块、不写 done 行，completed / gate_released_by_render 保持 False。
                stub.gate_timed_out = True
                self._end_chunked()
                return
            stub.gate_released_by_render = True

        self._write_line({"model": model, "message": {"role": "assistant", "content": last}, "done": False})
        self._write_line({"model": model, "done": True, "done_reason": "stop"})
        stub.completed = True
        self._end_chunked()


class OllamaStub:
    """`with OllamaStub() as stub:` 起一个只在 127.0.0.1 上监听、端口由内核分配的桩。

    可读回的状态：`request_count`（只数 `/api/chat`）、`payloads`（每次请求的 JSON 体）、
    `completed`（末块 + done 行确实发出去了）、`gate_released_by_render`（gate 是被 `set()`
    放行的，不是超时放行的）、`gate_timed_out`（gate 等满超时，桩走了干净收尾分支）。可从测试侧改的：`gate`（`threading.Event`）、`gate_mode`。
    """

    def __init__(
        self,
        *,
        deltas: Tuple[str, ...] = DELTAS,
        gate_mode: bool = False,
        gate_timeout_s: float = STUB_GATE_TIMEOUT,
    ) -> None:
        if len(deltas) < 2:
            raise ValueError("桩至少要两个 delta：gate 挡在「末块之前」，只有一块就没有「之前」")
        self.deltas: Tuple[str, ...] = tuple(deltas)
        self.gate_mode: bool = gate_mode
        self.gate_timeout_s: float = float(gate_timeout_s)
        self.gate = threading.Event()
        self.completed: bool = False
        self.gate_released_by_render: bool = False
        #: gate 等满 `gate_timeout_s` 仍未被 set()，桩已走了「干净收尾」分支。X-1c 用它断
        #: 「浏览器侧的 stop 收尾发生在桩放弃**之前**」——一个不掐表的因果断言。
        self.gate_timed_out: bool = False
        self.request_count: int = 0
        self.payloads: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    # ---- 生命周期 -----------------------------------------------------------------
    def start(self) -> "OllamaStub":
        if self._server is not None:
            return self
        server = ThreadingHTTPServer((_HOST, 0), _Handler)
        server.daemon_threads = True
        server.stub = self  # type: ignore[attr-defined]
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, name="ollama-stub", daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        server, self._server = self._server, None
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self) -> "OllamaStub":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    # ---- 只读属性 -----------------------------------------------------------------
    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("桩尚未启动")
        return int(self._server.server_address[1])

    @property
    def base_url(self) -> str:
        """给 `ai_settings.json` 的 `providers.ollama.base_url` 用：不带 `/v1`，不带尾斜杠。"""
        return f"http://{_HOST}:{self.port}"

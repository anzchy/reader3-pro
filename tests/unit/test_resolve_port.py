"""007 步骤 0.3 —— `--port` / `READER3_PORT` / 默认 8123 的优先级。

定义处：`docs/plans/20260816-tech-stack-migration/tasks/007-hygiene-and-contracts.md` 步骤 0.3。
规则一句话：**CLI 优先于 env，env 优先于 8123**。

优先级的三种组合都要单测，因为它们的失败是静默的：端口解错了服务照样起得来，
只是起在了别人身上——Playwright 撞开发者本地的 8123、CI 并发互相抢端口，
症状都不是「报错」而是「另一个进程的响应」。
"""

import pytest

from reader3_app.web.server import DEFAULT_PORT, resolve_port


def test_三者都缺时用默认端口():
    assert resolve_port(argv=[], env={}) == DEFAULT_PORT == 8123


def test_env_覆盖默认值():
    assert resolve_port(argv=[], env={"READER3_PORT": "9001"}) == 9001


def test_cli_覆盖默认值():
    assert resolve_port(argv=["--port", "9002"], env={}) == 9002


def test_cli_赢过_env():
    """优先级的核心断言：两个都给，CLI 说了算。"""
    assert resolve_port(argv=["--port", "9002"], env={"READER3_PORT": "9001"}) == 9002


def test_cli_等号写法():
    assert resolve_port(argv=["--port=9003"], env={}) == 9003


def test_忽略无关参数():
    assert resolve_port(argv=["--reload", "--port", "9004", "extra"], env={}) == 9004


def test_env_空字符串当作没给():
    """空 env 是「没设」不是「设成了空」——shell 里 `READER3_PORT=` 很常见。"""
    assert resolve_port(argv=[], env={"READER3_PORT": ""}) == DEFAULT_PORT
    assert resolve_port(argv=[], env={"READER3_PORT": "   "}) == DEFAULT_PORT


@pytest.mark.parametrize("bad", ["abc", "80.5", "-1", "0", "65536", "1e4"])
def test_非法端口报错而不是悄悄回落默认值(bad):
    """回落到 8123 会把「你写错了」伪装成「一切正常」——正是 0.3 要消灭的那类症状。"""
    with pytest.raises(ValueError) as e:
        resolve_port(argv=[], env={"READER3_PORT": bad})
    assert "READER3_PORT" in str(e.value)

    with pytest.raises(ValueError) as e:
        resolve_port(argv=["--port", bad], env={})
    assert "--port" in str(e.value)


def test_port_缺值时报错():
    with pytest.raises(ValueError) as e:
        resolve_port(argv=["--port"], env={})
    assert "--port" in str(e.value)


def test_边界端口可用():
    assert resolve_port(argv=["--port", "1"], env={}) == 1
    assert resolve_port(argv=["--port", "65535"], env={}) == 65535

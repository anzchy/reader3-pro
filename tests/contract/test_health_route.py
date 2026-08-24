"""007 步骤 0.3 —— `GET /api/health` 的状态码与载荷形状。

定义处：`docs/plans/20260816-tech-stack-migration/tasks/007-hygiene-and-contracts.md` 步骤 0.3。

它存在的唯一理由是**当就绪探针用**：009 的 Playwright `webServer` 靠它判断服务起没起来，
Phase 5 的 `reader3 launch` 复用同一条。所以它的契约有两条硬要求：
不碰磁盘（探针要快、要在书库为空时也能答），以及形状稳定（下游按字段读）。
"""

from fastapi.testclient import TestClient

from reader3_app.web.server import app

client = TestClient(app)


def test_返回_200():
    assert client.get("/api/health").status_code == 200


def test_载荷形状():
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert isinstance(body["version"], str) and body["version"]


def test_不依赖书库目录(tmp_path, monkeypatch):
    """探针在书库目录不存在时也必须返回 200。

    009 起的那个实例跑在临时目录里，书库常常是空的甚至不存在；
    探针一旦顺手去扫 books/ 就会在那里 500，而 webServer 只会报「服务没起来」。
    """
    monkeypatch.setattr("reader3_app.web.server.BOOKS_DIR", str(tmp_path / "nope"))
    assert client.get("/api/health").status_code == 200

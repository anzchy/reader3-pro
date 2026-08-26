"""Characterisation tests for routes that are currently broken.

These do **not** describe desired behaviour. They pin down what the code does
today, so that Phase 2's refactor cannot change it by accident — and so that
fixing it is a visible, deliberate act: the fix turns one of these red, and the
person fixing it rewrites the test into the contract table it belongs in.

Ownership note (008 三方并行分工): `src/` belonged to another agent while these
were written, so nothing here was a proposed patch — each defect was reported
with its file:line instead. Two of them were adjudicated and fixed at the end of
008; the tests that pinned them have been rewritten in place (see their
docstrings) rather than deleted, because the useful record is not the defect but
the fact that nothing had ever exercised the route.
"""

from __future__ import annotations

import pytest

from conftest import BOOK_ID, MISSING_BOOK_ID, World


@pytest.mark.parametrize(
    "book_id,expected",
    [(BOOK_ID, 200), (MISSING_BOOK_ID, 404)],
    ids=["existing", "missing"],
)
def test_读书首页路由渲染第一章而不是崩溃(world: World, book_id: str, expected: int) -> None:
    """`GET /read/{book_id}` 渲染 spine[0]，书不存在时 404。

    **这条测试是补丁，不是原稿。** 原稿断言的是 `pytest.raises(TypeError)`——
    `redirect_to_first_chapter` 转调 `read_chapter` 时漏了 `request` 参数，于是这条
    路由对**任何**输入都是 500，书存不存在都一样。CLAUDE.md 的数据流把它写成
    「点书 → 阅读页」的入口，而那个入口一直是死的；逃过人眼是因为书库页链接直接
    指向 `/read/{id}/0`，只有手敲 URL 的人会撞上。

    2026-08-24 随 008 修掉（`server.py` 的 `redirect_to_first_chapter` 显式接下
    `request` 再透传），本文件的原稿因此变红，按它自己 docstring 里写的约定改写成
    这条正常契约用例。**留在 `test_known_defects.py` 里而不是并进契约表，是因为
    它的价值在于记住这件事**：一条 100% 崩溃的路由能活到今天，唯一原因是没有任何
    东西打过它。

    抓住它的是 mypy 的 `call-arg`——本仓库开 mypy 的第一笔收益，所以
    `[tool.mypy]` 里那条不许被 `disable_error_code` 关掉。
    """
    resp = world.client.get(f"/read/{book_id}")
    assert resp.status_code == expected
    if expected == 200:
        # 断言真的渲染了第一章，而不是「返回了 200」——后者一个空模板也能满足。
        assert resp.headers["content-type"].startswith("text/html")
        assert world.client.get(f"/read/{book_id}/0").text == resp.text


def test_同一个越界章节号在两条路由上给出不同状态码(world: World) -> None:
    """章节号越界：reader 路由 404，notes 路由 400。两边都是现状，不一致本身是问题。

    `read_chapter` 判越界返回 404 "Chapter not found"（当前 server.py:496）；
    `api_get_chapter_notes` 对同样的越界返回 400 "Invalid chapter_index"
    （当前 server.py:665，另有 694 / 763 / 778 三处同样写法）。
    前端要为同一件事写两套分支。
    """
    out_of_range = 99
    assert world.client.get(f"/read/{BOOK_ID}/{out_of_range}").status_code == 404
    assert world.client.get(f"/api/notes/{BOOK_ID}/{out_of_range}").status_code == 400


def test_删除不存在的会话是幂等的204而不是404(world: World) -> None:
    """会话删除对「本来就没有」返回 204，其余资源的 DELETE 都返回 404。

    幂等删除是站得住脚的设计，但它在这份 API 里是孤例（collections / notes 的
    DELETE 都会 404）。冻结现状并记账，让 Phase 2 自己决定往哪边收口。
    """
    missing_conversation = "deadbeef-0000-4000-8000-000000000000"
    resp = world.client.delete(f"/api/ai/conversations/{world.book_uuid}/{missing_conversation}")
    assert resp.status_code == 204

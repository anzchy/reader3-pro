"""013 WI-12 functional rows: FB-S01..S08, FB-S09 (D8 subset), FD-17, FD-18, FA-07
(matrix C12.11-C12.17).

Every test that writes settings restores the sandbox `ai_settings.json` (its bytes or its
absence) afterwards, because the live server re-reads it on every request and the session
shares one server.

**Test-connection "ok" row (C12.11).** The frozen `ai_stub` only speaks the streaming NDJSON
shape of `POST /api/chat`; the connectivity test calls the same path with `stream: false` and
parses one JSON document, so against the stub the real route always answers
`success: false`. The fail row therefore runs end to end (browser -> server -> stub), and the
ok row fulfils the page's `/test` request with the route's documented success shape. What is
under test is that the page renders the two outcomes as distinct states.

**Deferred (user rulings).** FB-S09 (D8): only "a failed save shows a visible error and keeps
the input" is asserted, not stale-write detection. `set-export-json` (D11): a visible
「暂不支持」 line and 0 requests; its server half is backend debt "library export route".
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Iterator, List

import pytest
import shell_4a_fixtures as s4
import shell_4a_settings as ss
from playwright.sync_api import expect

pytestmark = pytest.mark.shell_4a

STATE_ATTR = "data-state"
ARIA_CHECKED = "aria-checked"
TYPE_ATTR = "type"
TRIPLE_CLICK_JS = "(el) => { el.click(); el.click(); el.click(); }"
OPTION_COUNT_JS = "(el) => (el.list ? el.list.options.length : -1)"
SAVE_PREFS = "保存偏好"
GUIDE_NAME = "未启用服务商"
EDITED_CHUNKS = "7"


def _sel(testid: str, provider: str) -> str:
    return f'[data-testid="{testid}"][data-provider="{provider}"]'


@pytest.fixture
def sandbox(e2e_books_dir: Path) -> Iterator[Path]:
    path = ss.sandbox_settings_path(e2e_books_dir)
    with ss.preserved_settings(path):
        yield path


@pytest.fixture
def ctx(browser: Any) -> Iterator[Any]:
    context = s4.new_gated_context(browser, init_scripts=[ss.ATTR_RECORDER_JS])
    try:
        yield context
    finally:
        context.close()


def _settle(page: Any, testid: str, provider: str | None = None) -> None:
    """Wait until the control is no longer busy (the in-flight request came back)."""
    sel = f'[data-testid="{testid}"]' + (f'[data-provider="{provider}"]' if provider else "")
    page.wait_for_function(
        "(sel) => { const el = document.querySelector(sel); return el && el.ariaBusy !== 'true'; }",
        arg=sel,
    )


def _busy_went_true_then_cleared(history: List[str | None]) -> bool:
    return "true" in history and history[-1] != "true"


# ---------------------------------------------------------------------------
# C12.11: single-flight for save / refresh / test; distinct test outcomes
# ---------------------------------------------------------------------------
def test_single_flight_and_test_states(ctx: Any, live_server: str, ai_settings_ollama: Path) -> None:
    page = ss.open_settings(ctx, live_server)
    log = ss.RequestLog(page).start()

    save = page.locator('[data-testid="set-provider-save"][data-provider="ollama"]')
    save.evaluate(TRIPLE_CLICK_JS)
    _settle(page, "set-provider-save", "ollama")
    expect(save).to_be_enabled()
    assert len(log.matching("PUT", "/api/settings/providers/ollama")) == 1, log.items
    assert _busy_went_true_then_cleared(ss.attr_history(page, "set-provider-save", "aria-busy", "ollama"))

    refresh = page.get_by_test_id("set-provider-refresh-models")
    refresh.evaluate(TRIPLE_CLICK_JS)
    _settle(page, "set-provider-refresh-models")
    assert len(log.matching("GET", "/api/ollama/models")) == 1, log.items
    assert _busy_went_true_then_cleared(ss.attr_history(page, "set-provider-refresh-models", "aria-busy"))

    # fail row, end to end through the stub
    test_btn = page.locator('[data-testid="set-provider-test"][data-provider="ollama"]')
    result = page.locator('[data-testid="set-provider-result"][data-provider="ollama"]')
    test_btn.evaluate(TRIPLE_CLICK_JS)
    expect(result).to_have_attribute(STATE_ATTR, "error")
    _settle(page, "set-provider-test", "ollama")
    assert len(log.matching("POST", "/api/settings/providers/ollama/test")) == 1, log.items
    assert _busy_went_true_then_cleared(ss.attr_history(page, "set-provider-test", "aria-busy", "ollama"))
    fail_text = result.inner_text()

    # ok row: the route's documented success shape
    page.route(
        "**/api/settings/providers/ollama/test",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"success": True, "provider": "ollama", "message": "OK",
                             "details": {"model": "stub-model", "latency_ms": 12}}),
        ),
    )
    test_btn.click()
    expect(result).to_have_attribute(STATE_ATTR, "ok")
    ok_text = result.inner_text()
    assert ok_text.strip() and fail_text.strip() and ok_text != fail_text, (ok_text, fail_text)


# ---------------------------------------------------------------------------
# C12.12 / FB-S01 / FA-07: switch semantics and persistence
# ---------------------------------------------------------------------------
def test_provider_toggle_switch(ctx: Any, live_server: str, sandbox: Path) -> None:
    page = ss.open_settings(ctx, live_server)
    toggle = page.locator('[data-testid="set-provider-toggle"][data-provider="ollama"]')
    expect(toggle).to_have_attribute("role", "switch")
    before = toggle.get_attribute(ARIA_CHECKED)
    assert before == "false", "ollama starts disabled in the default sandbox"
    log = ss.RequestLog(page).start()
    toggle.focus()
    page.keyboard.press(ss.KEY_SPACE)
    expect(toggle).to_have_attribute(ARIA_CHECKED, "true")
    page.keyboard.press(ss.KEY_SPACE)
    expect(toggle).to_have_attribute(ARIA_CHECKED, "false")
    page.keyboard.press(ss.KEY_ENTER)
    expect(toggle).to_have_attribute(ARIA_CHECKED, "true")
    _settle(page, "set-provider-toggle", "ollama")
    puts = log.matching("PUT", "/api/settings/providers/ollama")
    assert len(puts) == 3, f"three presses must persist three flips, not {len(puts)}"
    page.reload(wait_until="load")
    expect(page.get_by_test_id("set-provider-card")).to_have_count(len(ss.PROVIDERS))
    expect(toggle).to_have_attribute(ARIA_CHECKED, "true")
    stored = json.loads(sandbox.read_text(encoding="utf-8"))
    assert stored["providers"]["ollama"]["enabled"] is True


# ---------------------------------------------------------------------------
# C12.13 / FB-S04 / FD-17: a failed model refresh keeps the value and the options
# ---------------------------------------------------------------------------
def test_model_refresh_failure_keeps_value(ctx: Any, live_server: str, ai_settings_ollama: Path) -> None:
    calls: List[str] = []

    def status(route: Any) -> None:
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"running": True, "base_url": "http://127.0.0.1", "version": "stub"}))

    def models(route: Any) -> None:
        calls.append(route.request.url)
        if len(calls) == 1:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"models": [{"name": "alpha"}, {"name": "beta"}]}))
        else:
            route.continue_()  # the real server: the stub has no /api/tags, so 503

    page = ctx.new_page()
    page.route("**/api/ollama/status", status)
    page.route("**/api/ollama/models", models)
    page.goto(live_server + ss.SETTINGS_PATH, wait_until="load")
    expect(page.get_by_test_id("set-provider-card")).to_have_count(len(ss.PROVIDERS))
    model = page.locator('[data-testid="set-provider-model"][data-provider="ollama"]')
    expect(model).to_have_value("stub-model")
    page.wait_for_function(
        "(sel) => { const el = document.querySelector(sel); return !!(el && el.list && el.list.options.length === 2); }",
        arg=_sel("set-provider-model", "ollama"),
    )
    assert len(calls) == 1

    page.get_by_test_id("set-provider-refresh-models").click()
    result = page.locator('[data-testid="set-provider-result"][data-provider="ollama"]')
    expect(result).to_have_attribute(STATE_ATTR, "error")
    expect(result).to_be_visible()
    assert len(calls) == 2
    expect(model).to_have_value("stub-model")
    assert model.evaluate(OPTION_COUNT_JS) == 2, "a failed refresh must keep the known models"


# ---------------------------------------------------------------------------
# C12.14 / FB-S07: RAG inputs clamp and persist
# ---------------------------------------------------------------------------
CLAMP_ROWS = {
    "low": (("0", "1"), ("999", "1000")),
    "high": (("21", "20"), ("32001", "32000")),
}


@pytest.mark.parametrize("row", list(CLAMP_ROWS))
def test_rag_inputs_clamp_and_persist(ctx: Any, live_server: str, sandbox: Path, row: str) -> None:
    (chunks_in, chunks_out), (context_in, context_out) = CLAMP_ROWS[row]
    page = ss.open_settings(ctx, live_server)
    chunks = page.get_by_test_id("set-rag-chunks")
    context_window = page.get_by_test_id("set-rag-context")
    chunks.fill(chunks_in)
    chunks.blur()
    expect(chunks).to_have_value(chunks_out)
    context_window.fill(context_in)
    context_window.blur()
    expect(context_window).to_have_value(context_out)
    with page.expect_response(lambda r: r.request.method == "PUT" and r.url.endswith("/api/settings")) as resp:
        page.get_by_role("button", name=SAVE_PREFS).click()
    assert resp.value.ok
    body = json.loads(resp.value.request.post_data or "{}")
    assert body["preferences"]["rag_chunks"] == int(chunks_out)
    assert body["preferences"]["rag_context_window"] == int(context_out)
    page.reload(wait_until="load")
    expect(page.get_by_test_id("set-provider-card")).to_have_count(len(ss.PROVIDERS))
    expect(chunks).to_have_value(chunks_out)
    expect(context_window).to_have_value(context_out)


# ---------------------------------------------------------------------------
# C12.15 / FB-S08 / FB-S06: the key is never echoed; exports
# ---------------------------------------------------------------------------
def test_key_never_echoed_and_exports(ctx: Any, live_server: str, sandbox: Path) -> None:
    secret = "sk-wi12-" + uuid.uuid4().hex
    page = ss.open_settings(ctx, live_server)
    responses: List[Any] = []
    page.on("response", lambda r: responses.append(r))  # a builtin bound method cannot be a Playwright handler

    key = page.locator('[data-testid="set-provider-key"][data-provider="openai"]')
    assert key.get_attribute(TYPE_ATTR) == "password"
    key.fill(secret)
    with page.expect_response(lambda r: r.request.method == "PUT" and "/api/settings/providers/openai" in r.url):
        page.locator('[data-testid="set-provider-save"][data-provider="openai"]').click()
    expect(key).to_have_value("")
    assert secret in sandbox.read_text(encoding="utf-8"), "the key was not saved server-side"

    page.reload(wait_until="load")
    expect(page.get_by_test_id("set-provider-card")).to_have_count(len(ss.PROVIDERS))
    assert key.get_attribute(TYPE_ATTR) == "password"
    expect(key).to_have_value("")
    assert secret not in page.content(), "the key is in the rendered page"

    export = page.get_by_test_id("set-export-settings")
    with page.expect_download() as dl:
        export.click()
    text = Path(dl.value.path()).read_text(encoding="utf-8")
    exported = json.loads(text)
    assert isinstance(exported, dict) and exported, "the settings export is empty"
    assert secret not in text, "the settings export contains the key"
    expect(export).to_be_enabled()
    disabled = ss.attr_history(page, "set-export-settings", "disabled")
    assert any(v is not None for v in disabled), "set-export-settings was never disabled while exporting"
    assert disabled[-1] is None, f"set-export-settings stayed disabled: {disabled}"

    for r in responses:
        if "/api/" not in r.url:
            continue
        try:
            body = r.text()
        except Exception:  # noqa: BLE001 - a body the browser no longer holds cannot hold the key either
            continue
        assert secret not in body, f"{r.url} echoed the key"

    log = ss.RequestLog(page).start()
    page.get_by_test_id("set-export-json").click()
    expect(page.get_by_text("暂不支持")).to_be_visible()
    assert log.items == [], f"set-export-json sent requests: {log.items}"


# ---------------------------------------------------------------------------
# C12.16 / FB-S09 (D8 subset): a failed save is visible and keeps the input
# ---------------------------------------------------------------------------
def test_save_failure_is_visible(ctx: Any, live_server: str, sandbox: Path) -> None:
    page = ss.open_settings(ctx, live_server)

    def fail_put(route: Any) -> None:
        if route.request.method == "PUT":
            route.fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "boom"}))
        else:
            route.continue_()

    page.route("**/api/settings", fail_put)
    chunks = page.get_by_test_id("set-rag-chunks")
    chunks.fill(EDITED_CHUNKS)
    chunks.blur()
    page.get_by_role("button", name=SAVE_PREFS).click()
    alert = page.get_by_role("alert")
    expect(alert).to_be_visible()
    expect(alert).to_contain_text("保存失败")
    expect(chunks).to_have_value(EDITED_CHUNKS)


PROVIDER_SAVE_FAILED = "保存没有成功"
EDITED_MODEL = "edited-model-rv1"


def test_provider_save_failure_is_visible(ctx: Any, live_server: str, sandbox: Path) -> None:
    """FB-S09 (D8 remainder, 013 final review RV-1): a failed provider-card save is visible.

    The card's own save PUT is failed in the browser (a 500 with a detail); the card's result
    line shows the error state and text, and the edited model value stays in the field.
    """
    page = ss.open_settings(ctx, live_server)
    puts: List[str] = []

    def fail_put(route: Any) -> None:
        if route.request.method == "PUT":
            puts.append(route.request.url)
            route.fulfill(status=500, content_type="application/json", body=json.dumps({"detail": "boom"}))
        else:
            route.continue_()

    page.route("**/api/settings/providers/ollama", fail_put)
    before = sandbox.read_bytes() if sandbox.exists() else None
    model = page.locator(_sel("set-provider-model", "ollama"))
    model.fill(EDITED_MODEL)
    page.locator(_sel("set-provider-save", "ollama")).click()

    result = page.locator(_sel("set-provider-result", "ollama"))
    expect(result).to_have_attribute(STATE_ATTR, "error")
    expect(result).to_be_visible()
    expect(result).to_contain_text(PROVIDER_SAVE_FAILED)
    expect(result).to_contain_text("boom")
    _settle(page, "set-provider-save", "ollama")
    assert len(puts) == 1, puts
    expect(model).to_have_value(EDITED_MODEL)
    # Only this card reports the failure.
    expect(page.locator(_sel("set-provider-result", "openai"))).not_to_have_attribute(STATE_ATTR, "error")
    after = sandbox.read_bytes() if sandbox.exists() else None
    assert after == before, "a save the browser saw fail must not have reached the settings file"


# ---------------------------------------------------------------------------
# C12.17 / FD-18: the empty-provider guide
# ---------------------------------------------------------------------------
def test_empty_provider_guide(ctx: Any, live_server: str, sandbox: Path) -> None:
    ss.write_settings(sandbox, ss.all_disabled_settings())
    page = ss.open_settings(ctx, live_server)
    guide = page.get_by_role("note", name=GUIDE_NAME)
    expect(guide).to_be_visible()
    for p in ss.PROVIDERS:
        expect(page.locator(_sel("set-provider-toggle", p))).to_have_attribute(ARIA_CHECKED, "false")
    page.locator('[data-testid="set-provider-toggle"][data-provider="ollama"]').click()
    expect(guide).to_be_hidden()


def test_guide_hidden_when_a_provider_is_enabled(ctx: Any, live_server: str, ai_settings_ollama: Path) -> None:
    page = ss.open_settings(ctx, live_server)
    expect(page.get_by_role("note", name=GUIDE_NAME)).to_be_hidden()
    expect(page.locator('[data-testid="set-provider-toggle"][data-provider="ollama"]')).to_have_attribute(
        ARIA_CHECKED, "true"
    )

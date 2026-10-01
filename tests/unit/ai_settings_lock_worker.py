"""Child-process body for ``test_ai_settings_lock.py::test_processes_conserve_all_updates``.

Lives in its own module, not in the test file, for the same reason
``notes_concurrency.py`` does: a ``spawn`` child re-imports the target's module
by name, and this one imports nothing but the code under test.
"""

from __future__ import annotations

from typing import Any


def rmw_under_transaction(path: str, provider: str, index: int, iterations: int, start: Any) -> None:
    """Wait for the start signal, then run ``iterations`` locked read-modify-write cycles."""
    from reader3_app.ai.config import ai_settings_transaction, load_ai_settings, save_ai_settings

    if not start.wait(30):
        raise SystemExit(3)
    for k in range(iterations):
        with ai_settings_transaction(path):
            settings = load_ai_settings(path=path)
            settings["providers"][provider]["model_name"] = f"w{index}-{k}"
            save_ai_settings(settings, path=path)

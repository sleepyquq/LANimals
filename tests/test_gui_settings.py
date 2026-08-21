"""设置页与后台控制器的异步接线回归测试。"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from lanimals.gui.qt_theme import current_theme
from lanimals.gui.views import SettingsView


class _FakeController:
    local_only = False
    selected_adapter: str | None = None

    def __init__(self) -> None:
        self.max_upload_size = "2GB"
        self.applied_settings: list[tuple[bool, str | None, str]] = []

    def get_max_upload_size(self) -> str:
        return self.max_upload_size

    def apply_settings(self, *, local_only: bool, adapter_name: str | None, max_upload_size: str) -> str:
        self.applied_settings.append((local_only, adapter_name, max_upload_size))
        self.local_only = local_only
        self.selected_adapter = adapter_name
        self.max_upload_size = max_upload_size
        return max_upload_size

    def get_lan_candidates(self) -> list[tuple[str, str]]:
        return [("Wi-Fi", "192.168.1.20")]

class _QueuedApp:
    def __init__(self) -> None:
        self.controller = _FakeController()
        self._pending: tuple[Callable[[], Any], Callable[[Any], None] | None, Callable[[Exception], None] | None] | None = None

    def run_controller_action(
        self,
        action: Callable[[], Any],
        *,
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._pending = (action, on_success, on_error)

    def finish_action(self) -> None:
        assert self._pending is not None
        action, on_success, on_error = self._pending
        self._pending = None
        try:
            result = action()
        except Exception as error:  # pragma: no cover - fake controller不抛异常
            assert on_error is not None
            on_error(error)
        else:
            if on_success is not None:
                on_success(result)


@pytest.fixture(scope="module")
def qt_application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_save_and_restart_applies_all_staged_settings_in_one_controller_action(qt_application: QApplication) -> None:
    app = _QueuedApp()
    view = SettingsView(app, current_theme())
    view.refresh_settings()

    view.upload_entry.setText("1.5")
    view.lan_switch.click()
    view.adapter_menu.setCurrentIndex(1)
    view._on_save_settings()

    assert app.controller.applied_settings == []
    assert app._pending is not None
    assert not view.upload_entry.isEnabled()
    assert not view.lan_switch.isEnabled()
    assert not view.adapter_menu.isEnabled()

    app.finish_action()

    assert app.controller.applied_settings == [(True, "Wi-Fi", "1.5GB")]
    assert view.upload_entry.isEnabled()
    assert view.upload_error_label.text() == ""


def test_lan_switch_is_staged_until_save_and_restart_is_clicked(qt_application: QApplication) -> None:
    app = _QueuedApp()
    view = SettingsView(app, current_theme())
    view.refresh_settings()

    view.lan_switch.click()

    assert app._pending is None
    assert app.controller.local_only is False
    assert view.save_restart_button.isEnabled()

    view._on_save_settings()
    app.finish_action()

    assert app.controller.local_only is True
    assert view.lan_switch.isEnabled()
    assert not view.adapter_menu.isEnabled()

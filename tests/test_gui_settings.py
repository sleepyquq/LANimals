"""设置页与后台控制器的异步接线回归测试。"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from lanimals.gui.i18n import t
from lanimals.gui.qt_theme import current_theme
from lanimals.gui.views import SettingsView


class _FakeController:
    local_only = False
    selected_adapter: str | None = None
    use_domain = True
    ip_url = "http://192.168.1.20:8787/"

    def __init__(self) -> None:
        self.max_upload_size = "2GB"
        self.applied_settings: list[tuple[bool, str | None, str]] = []

    def get_max_upload_size(self) -> str:
        return self.max_upload_size

    def apply_settings(
        self,
        *,
        local_only: bool,
        adapter_name: str | None,
        max_upload_size: str,
        use_domain: bool = True,
    ) -> str:
        self.applied_settings.append((local_only, adapter_name, max_upload_size))
        self.use_domain = use_domain
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

    # 没有改动时“保存并重启”不可点，避免无意义的重启。
    assert not view.save_restart_button.isEnabled()

    view.upload_entry.setText("1.5")
    view.adapter_menu.setCurrentIndex(1)
    assert view.save_restart_button.isEnabled()
    view._on_save_settings()

    assert app.controller.applied_settings == []
    assert app._pending is not None
    assert not view.upload_entry.isEnabled()
    assert not view.adapter_menu.isEnabled()
    assert not view.save_restart_button.isEnabled()

    app.finish_action()

    # 局域网访问已移到主页，保存设置时沿用控制器当前的访问模式。
    assert app.controller.applied_settings == [(False, "Wi-Fi", "1.5GB")]
    assert view.upload_entry.isEnabled()
    assert view.upload_error_label.text() == ""
    assert not view.save_restart_button.isEnabled()


def test_settings_page_no_longer_owns_the_lan_switch(qt_application: QApplication) -> None:
    app = _QueuedApp()
    app.controller.local_only = True
    view = SettingsView(app, current_theme())
    view.refresh_settings()

    assert not hasattr(view, "lan_switch")
    # 仅本机模式下网卡选择没有意义。
    assert not view.adapter_menu.isEnabled()


def test_invalid_upload_size_is_reported_without_saving(qt_application: QApplication) -> None:
    app = _QueuedApp()
    view = SettingsView(app, current_theme())
    view.refresh_settings()

    view.upload_entry.setText("abc")
    view._on_save_settings()

    assert app._pending is None
    assert view.upload_error_label.text() == t("gui.maxUploadSizeInvalid")


@pytest.mark.parametrize("button_name", ["save_restart_button", "clear_button"])
def test_bottom_buttons_are_compact_and_centered(qt_application: QApplication, button_name: str) -> None:
    """底部按钮按文字宽度收紧并居中；清除按钮的悬停底色也不能横跨整行。"""
    app = _QueuedApp()
    view = SettingsView(app, current_theme())
    view.resize(340, 394)
    view.show()
    try:
        qt_application.processEvents()

        button = getattr(view, button_name)
        center = button.geometry().center().x()
        # 与字体无关：按钮宽度等于文字所需宽度（没有被拉伸到整行），且水平居中。
        # CI 的 Windows 镜像缺少字体，按页面宽度比例断言会因字宽不同而误报。
        assert button.width() == button.sizeHint().width()
        assert abs(center - view.width() / 2) <= 2
    finally:
        view.hide()


def test_fixed_domain_toggle_is_staged_and_shows_backup_ip(qt_application: QApplication) -> None:
    app = _QueuedApp()
    view = SettingsView(app, current_theme())
    view.refresh_settings()

    assert view.domain_switch.isChecked()
    # 启用固定域名时，IP 作为备用地址显示在该设置下。
    assert not view.backup_ip_label.isHidden()
    assert view.backup_ip_label.text().endswith("192.168.1.20:8787")

    view.domain_switch.click()
    assert view.save_restart_button.isEnabled()
    view._on_save_settings()
    app.finish_action()

    assert app.controller.applied_settings == [(False, None, "2GB")]
    assert app.controller.use_domain is False
    assert not view.domain_switch.isChecked()
    assert view.backup_ip_label.isHidden()

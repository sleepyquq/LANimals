"""系统托盘（Qt 原生 QSystemTrayIcon）回归测试。"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from lanimals.gui import tray as tray_module
from lanimals.gui.i18n import t
from lanimals.gui.tray import SystemTray


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def qt_application() -> QApplication:
    return QApplication.instance() or QApplication([])


class _Calls:
    def __init__(self) -> None:
        self.events: list[str] = []

    def tray(self) -> SystemTray:
        return SystemTray(
            on_show=lambda: self.events.append("show"),
            on_open_browser=lambda: self.events.append("open"),
            on_toggle_server=lambda: self.events.append("toggle"),
            on_exit=lambda: self.events.append("exit"),
        )


def test_pystray_is_fully_replaced_by_the_qt_tray() -> None:
    """pystray 在 macOS 必须独占主线程，与 Qt 事件循环冲突；三平台统一用 Qt 原生托盘。"""
    for relative in ("pyproject.toml", "requirements.txt", "scripts/build_app.py", "lanimals/gui/tray.py"):
        assert "pystray" not in (PROJECT_ROOT / relative).read_text(encoding="utf-8"), relative


def test_constructing_the_tray_does_not_touch_the_native_backend(qt_application: QApplication) -> None:
    tray = _Calls().tray()
    assert tray.available is False
    assert tray._icon is None


def test_tray_degrades_gracefully_when_the_desktop_has_no_tray(
    qt_application: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tray_module.QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: False))
    tray = _Calls().tray()
    tray.start()
    assert tray.available is False
    assert tray._icon is None
    tray.stop()


def test_tray_menu_and_activation_drive_the_window_callbacks(
    qt_application: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tray_module.QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    calls = _Calls()
    tray = calls.tray()
    tray.start()
    try:
        assert tray.available is True
        assert tray._icon is not None
        assert not tray._icon.icon().isNull()
        assert tray._icon.toolTip() == "LANimals"

        actions = [action for action in tray._icon.contextMenu().actions() if not action.isSeparator()]
        assert [action.text() for action in actions] == [
            t("gui.trayShow"),
            t("gui.trayOpen"),
            t("gui.trayToggle"),
            t("gui.trayExit"),
        ]
        for action in actions:
            action.trigger()
        assert calls.events == ["show", "open", "toggle", "exit"]

        calls.events.clear()
        monkeypatch.setattr(tray_module.sys, "platform", "win32")
        tray._on_activated(QSystemTrayIcon.ActivationReason.Trigger)
        tray._on_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
        tray._on_activated(QSystemTrayIcon.ActivationReason.Context)
        assert calls.events == ["show", "show"]

        # macOS 单击菜单栏图标由系统弹出菜单，不应同时把窗口抢到前台。
        calls.events.clear()
        monkeypatch.setattr(tray_module.sys, "platform", "darwin")
        tray._on_activated(QSystemTrayIcon.ActivationReason.Trigger)
        assert calls.events == []
    finally:
        tray.stop()
    assert tray.available is False
    assert tray._icon is None


@pytest.mark.parametrize(("tray_available", "expect_hidden"), [(True, True), (False, False)])
def test_close_button_never_strands_the_window_without_a_tray(
    qt_application: QApplication, tmp_path, monkeypatch: pytest.MonkeyPatch, tray_available: bool, expect_hidden: bool
) -> None:
    """没有托盘的桌面（如未装扩展的 GNOME）上，关闭按钮改为最小化，窗口不会无处可找。"""
    from PySide6.QtCore import QEvent

    from lanimals.gui import app as app_module

    monkeypatch.setattr(app_module.SystemTray, "start", lambda _tray: None)
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.LANimalsApp(data_dir=tmp_path / "data")
    minimized: list[bool] = []
    monkeypatch.setattr(window, "showMinimized", lambda: minimized.append(True))
    monkeypatch.setattr(type(window.tray), "available", property(lambda _tray: tray_available))
    try:
        window.show()
        window.hide_to_tray()
        assert window.isHidden() is expect_hidden
        assert minimized == ([] if expect_hidden else [True])
    finally:
        window._quitting = True
        window.close()
        window.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

"""控制面板跨平台行为（拖动、字体、最小化、系统语言）的回归测试。"""

from __future__ import annotations

import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from lanimals.gui import i18n
from lanimals.gui.widgets import DragRegion


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def qt_application() -> QApplication:
    return QApplication.instance() or QApplication([])


class _FakeHandle:
    def __init__(self, supported: bool) -> None:
        self.supported = supported
        self.system_moves = 0

    def startSystemMove(self) -> bool:  # noqa: N802 - Qt API 命名
        self.system_moves += 1
        return self.supported


class _FakeWindow:
    def __init__(self, supported: bool) -> None:
        self.handle = _FakeHandle(supported)
        self.position = QPoint(100, 100)

    def windowHandle(self) -> _FakeHandle:  # noqa: N802 - Qt API 命名
        return self.handle

    def pos(self) -> QPoint:
        return self.position

    def move(self, position: QPoint) -> None:
        self.position = position


def _mouse(kind: QMouseEvent.Type, x: int, y: int, buttons: Qt.MouseButton) -> QMouseEvent:
    point = QPointF(x, y)
    return QMouseEvent(kind, point, point, point, Qt.MouseButton.LeftButton, buttons, Qt.KeyboardModifier.NoModifier)


def test_title_bar_drag_prefers_the_native_system_move(qt_application: QApplication) -> None:
    """Wayland 禁止应用自行定位窗口；系统移动可用时必须交给窗口管理器处理拖动与贴边。"""
    window = _FakeWindow(supported=True)
    region = DragRegion(window)  # type: ignore[arg-type]

    region.mousePressEvent(_mouse(QMouseEvent.Type.MouseButtonPress, 10, 10, Qt.MouseButton.LeftButton))
    region.mouseMoveEvent(_mouse(QMouseEvent.Type.MouseMove, 40, 30, Qt.MouseButton.LeftButton))

    assert window.handle.system_moves == 1
    assert window.position == QPoint(100, 100)


def test_title_bar_drag_falls_back_to_manual_move(qt_application: QApplication) -> None:
    window = _FakeWindow(supported=False)
    region = DragRegion(window)  # type: ignore[arg-type]

    region.mousePressEvent(_mouse(QMouseEvent.Type.MouseButtonPress, 10, 10, Qt.MouseButton.LeftButton))
    region.mouseMoveEvent(_mouse(QMouseEvent.Type.MouseMove, 40, 30, Qt.MouseButton.LeftButton))

    assert window.handle.system_moves == 1
    assert window.position == QPoint(130, 120)


@pytest.mark.parametrize(
    ("platform", "ui_family", "mono_family"),
    [
        ("win32", "Microsoft YaHei UI", "Consolas"),
        ("darwin", "PingFang SC", "Menlo"),
        ("linux", "Noto Sans CJK SC", "DejaVu Sans Mono"),
    ],
)
def test_fonts_follow_the_host_platform(platform: str, ui_family: str, mono_family: str) -> None:
    from lanimals.gui.qt_theme import mono_font_families, ui_font_families

    assert ui_font_families(platform)[0] == ui_family
    assert mono_font_families(platform)[0] == mono_family


def test_qt_widgets_do_not_hard_code_windows_only_fonts() -> None:
    offenders = []
    for path in (PROJECT_ROOT / "lanimals/gui").glob("*.py"):
        if path.name in {"qt_theme.py", "theme.py"}:
            continue
        source = path.read_text(encoding="utf-8")
        for family in ("Microsoft YaHei UI", "Consolas", "Segoe UI"):
            if re.search(re.escape(family), source):
                offenders.append(f"{path.name}: {family}")
    assert offenders == []


def test_macos_frameless_window_keeps_a_minimize_hint() -> None:
    """macOS 上无边框窗口缺少最小化提示时 showMinimized() 不生效。"""
    from lanimals.gui.app import window_flags_for_platform

    mac_flags = window_flags_for_platform("darwin")
    assert mac_flags & Qt.WindowType.FramelessWindowHint
    assert mac_flags & Qt.WindowType.WindowMinimizeButtonHint

    # Windows 保持已调试稳定的窗口标志不变。
    assert window_flags_for_platform("win32") == Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint


@pytest.mark.parametrize(
    ("languages", "expected"),
    [
        (["zh-Hans-CN", "en-US"], "zh-CN"),
        (["zh-CN"], "zh-CN"),
        (["en-US", "zh-CN"], "en"),
        ([], "en"),
    ],
)
def test_system_language_uses_the_platform_ui_languages(
    monkeypatch: pytest.MonkeyPatch, languages: list[str], expected: str
) -> None:
    """macOS 从访达启动时通常没有 LANG 环境变量，必须读取系统界面语言设置。"""
    monkeypatch.setattr(i18n.sys, "platform", "darwin")
    monkeypatch.setattr(i18n, "_system_ui_languages", lambda: languages)
    assert i18n._detect_system_language() == expected


def test_system_language_detection_avoids_deprecated_locale_api() -> None:
    assert "getdefaultlocale" not in (PROJECT_ROOT / "lanimals/gui/i18n.py").read_text(encoding="utf-8")


def test_non_windows_application_font_prefers_platform_cjk_families(
    qt_application: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Linux 默认字体常不含中文字形；按钮等未单独设字体的控件也要走平台中文字体。"""
    from lanimals.gui.app import apply_platform_application_font
    from lanimals.gui.qt_theme import ui_font_families

    original = qt_application.font()
    try:
        monkeypatch.setattr("lanimals.gui.app.sys.platform", "linux")
        apply_platform_application_font(qt_application)
        font = qt_application.font()
        assert font.families()[: len(ui_font_families("linux"))] == ui_font_families("linux")
        assert font.pointSizeF() == original.pointSizeF()

        # Windows 保持系统默认界面字体不变。
        qt_application.setFont(original)
        monkeypatch.setattr("lanimals.gui.app.sys.platform", "win32")
        apply_platform_application_font(qt_application)
        assert qt_application.font() == original
    finally:
        qt_application.setFont(original)

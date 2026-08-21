"""Qt 桌面端布局与无闪帧窗口外壳回归测试。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from lanimals.gui.motion import ease_out_cubic
from lanimals.gui.theme import load_app_icon_image


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _source(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_settings_view_is_fixed_and_uses_warm_native_controls() -> None:
    source = _source("lanimals/gui/views.py")

    assert "QScrollArea" not in source
    assert "QComboBox" in source
    assert "QLineEdit" in source
    assert "self.lan_switch = AnimatedToggle(" in source
    assert "WarmComboBox" in source
    assert "QComboBox QAbstractItemView" in source
    assert "QFrame#settings-card" in source
    assert 'setObjectName("settings-card")' in source
    assert "layout.addStretch(1)" in source


def test_settings_field_labels_use_a_compact_shared_text_style() -> None:
    source = _source("lanimals/gui/views.py")

    assert "def _settings_field_label(" in source
    assert 'QFont("Microsoft YaHei UI", 10, QFont.Weight.Medium)' in source
    assert source.count("_settings_field_label(") >= 4


def test_settings_header_and_window_controls_use_shared_hover_widget() -> None:
    app_source = _source("lanimals/gui/app.py")
    widget_source = _source("lanimals/gui/widgets.py")

    assert "self.page_header_layout" in app_source
    assert "HoverToolButton(\"←\"" in app_source
    assert "HoverToolButton(\"−\"" in app_source
    assert "HoverToolButton(\"×\"" in app_source
    assert "QToolButton:hover" in widget_source


def test_gui_uses_content_only_page_and_toggle_animations() -> None:
    app_source = _source("lanimals/gui/app.py")
    widget_source = _source("lanimals/gui/widgets.py")

    assert "PageHost" in app_source
    assert "QPropertyAnimation" in widget_source
    assert "self._animation.setDuration(160)" in widget_source
    assert "QEasingCurve.Type.OutCubic" in widget_source
    assert "incoming_animation.setDuration(180)" in widget_source
    assert "只动画页面内容" in widget_source
    page_host = widget_source.split("class PageHost", maxsplit=1)[1]
    transition_branch = page_host.split("width = max(1, self.width())", maxsplit=1)[1]
    assert transition_branch.index("outgoing.hide()") < transition_branch.index("incoming.show()")
    assert "outgoing_animation" not in page_host


def test_gui_uses_qt_owned_frameless_taskbar_shell_without_tk_rewrites() -> None:
    app_source = _source("lanimals/gui/app.py")
    package_source = _source("lanimals/gui/__init__.py")

    assert "class LANimalsApp(QMainWindow)" in app_source
    assert "Qt.WindowType.FramelessWindowHint" in app_source
    assert "self.setFixedSize(340, 430)" in app_source
    assert "self.showMinimized()" in app_source
    assert "self.showNormal()" in app_source
    assert "WA_OpaquePaintEvent" in app_source
    assert "SetWindowLong" not in app_source
    assert "overrideredirect" not in app_source
    assert "CustomTkinter" not in app_source
    assert "_set_window_alpha" not in app_source
    assert "_play_content_reveal_animation" not in app_source
    assert "LANimalsApp" in package_source


def test_main_view_and_tray_use_the_same_canonical_icon_as_the_taskbar() -> None:
    """主页小猫和托盘图标必须来自窗口 .ico 所对应的同一张 PNG 资源。"""
    views_source = _source("lanimals/gui/views.py")
    tray_source = _source("lanimals/gui/tray.py")

    assert "load_app_icon_image(28)" in views_source
    assert "load_app_icon_image(size)" in tray_source

    icon_path = PROJECT_ROOT / "lanimals/gui/assets/icon.png"
    with Image.open(icon_path) as source:
        expected = source.convert("RGBA").resize((28, 28), Image.Resampling.LANCZOS)
    assert load_app_icon_image(28).tobytes() == expected.tobytes()


def test_ease_out_cubic_has_a_fast_start_and_safe_bounds() -> None:
    assert ease_out_cubic(-1.0) == 0.0
    assert ease_out_cubic(0.0) == 0.0
    assert ease_out_cubic(1.0) == 1.0
    assert ease_out_cubic(2.0) == 1.0
    assert 0.5 < ease_out_cubic(0.5) < 1.0

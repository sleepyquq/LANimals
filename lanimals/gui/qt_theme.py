"""LANimals Qt 桌面端的暖色主题定义。"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication

# 主窗口外壳圆角；无原生圆角的平台由窗口自身按该半径绘制并裁剪遮罩。
WINDOW_CORNER_RADIUS = 8

# 每个平台优先使用系统自带的中文界面字体，其后是同平台的常见回退。
_UI_FONT_FAMILIES = {
    "win32": ("Microsoft YaHei UI", "Segoe UI"),
    "darwin": ("PingFang SC", "Hiragino Sans GB", "Helvetica Neue"),
    "linux": ("Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei", "Noto Sans", "DejaVu Sans"),
}
_MONO_FONT_FAMILIES = {
    "win32": ("Consolas", "Cascadia Mono", "Courier New"),
    "darwin": ("Menlo", "SF Mono", "Monaco"),
    "linux": ("DejaVu Sans Mono", "Noto Sans Mono", "Liberation Mono", "monospace"),
}


def _platform_key(platform: str | None) -> str:
    # 在调用时读取 sys.platform，而不是在导入时把默认参数固定下来。
    platform = sys.platform if platform is None else platform
    if platform in ("win32", "darwin"):
        return platform
    return "linux"


def ui_font_families(platform: str | None = None) -> list[str]:
    return list(_UI_FONT_FAMILIES[_platform_key(platform)])


def mono_font_families(platform: str | None = None) -> list[str]:
    return list(_MONO_FONT_FAMILIES[_platform_key(platform)])


def ui_font(point_size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """当前平台的界面字体；缺失时由 Qt 依次回退，而不是直接落到默认字体。"""
    font = QFont()
    font.setFamilies(ui_font_families())
    font.setPointSize(point_size)
    font.setWeight(weight)
    return font


def mono_font(point_size: int) -> QFont:
    font = QFont()
    font.setFamilies(mono_font_families())
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(point_size)
    return font


def ui_font_css() -> str:
    """供样式表 font-family 使用的同一组平台字体。"""
    return ", ".join(f"'{family}'" for family in ui_font_families())


@dataclass(frozen=True)
class QtTheme:
    """集中保存 Qt 控件所需颜色，避免页面各自拼接不一致的样式。"""

    is_dark: bool
    background: str
    card: str
    card_border: str
    text_main: str
    text_muted: str
    text_subtle: str
    link: str
    link_hover: str
    secondary_button: str
    secondary_hover: str
    secondary_text: str
    top_control_hover: str
    entry_background: str
    entry_border: str
    accent: str
    accent_hover: str
    danger: str
    danger_hover: str
    status_green: str
    status_gray: str


def current_theme() -> QtTheme:
    """按系统配色生成一次主题；窗口运行期不触发额外的样式重建。"""
    hints = QGuiApplication.styleHints()
    is_dark = hints.colorScheme() == Qt.ColorScheme.Dark
    if is_dark:
        return QtTheme(
            is_dark=True,
            background="#181614",
            card="#23201c",
            card_border="#3b342b",
            text_main="#f6f1eb",
            text_muted="#a89c91",
            text_subtle="#73685e",
            link="#a89c91",
            link_hover="#60a5fa",
            secondary_button="#302b25",
            secondary_hover="#3f3830",
            secondary_text="#dfd3c4",
            top_control_hover="#39332c",
            entry_background="#2b2722",
            entry_border="#423b32",
            accent="#f08c35",
            accent_hover="#e07e24",
            danger="#ef5350",
            danger_hover="#e53935",
            status_green="#55c46b",
            status_gray="#b2a89f",
        )
    return QtTheme(
        is_dark=False,
        background="#faf6ee",
        card="#ffffff",
        card_border="#ebdcc7",
        text_main="#2c2520",
        text_muted="#82756a",
        text_subtle="#a99c90",
        link="#5c534a",
        link_hover="#2563eb",
        secondary_button="#f4ebd9",
        secondary_hover="#e8dcc6",
        secondary_text="#5c4a38",
        top_control_hover="#eee4d6",
        entry_background="#fdfbf7",
        entry_border="#e5d7c3",
        accent="#f08c35",
        accent_hover="#d9751e",
        danger="#c62828",
        danger_hover="#b71c1c",
        status_green="#55c46b",
        status_gray="#b2a89f",
    )

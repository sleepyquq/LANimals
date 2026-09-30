"""控制面板实际绘制结果（英文文字、窗口圆角外侧）的回归测试。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from lanimals.gui import i18n
from lanimals.gui.dialogs import ClearDataDialog, PasswordDialog
from lanimals.gui.i18n import init_i18n, t
from lanimals.gui.qt_theme import current_theme
from lanimals.gui.views import SettingsView
from tests.test_gui_settings import _QueuedApp


@pytest.fixture()
def english(qt_application: QApplication):
    names = ("_CURRENT_TRANSLATIONS", "_FALLBACK_TRANSLATIONS", "_INITIALIZED")
    saved = {name: getattr(i18n, name) for name in names}
    init_i18n("en")
    yield
    for name, value in saved.items():
        setattr(i18n, name, value)


@pytest.fixture(scope="module")
def qt_application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _displayed(button: QPushButton) -> str:
    """还原 Qt 按钮实际绘制的文字：单个 & 是助记符标记，&& 才显示为 &。"""
    text = button.text()
    shown = []
    index = 0
    while index < len(text):
        if text[index] == "&":
            if text[index + 1 : index + 2] == "&":
                shown.append("&")
                index += 2
                continue
            index += 1
            continue
        shown.append(text[index])
        index += 1
    return "".join(shown)


def test_settings_buttons_show_ampersands_literally(english) -> None:
    app = _QueuedApp()
    view = SettingsView(app, current_theme())

    assert _displayed(view.save_restart_button) == "Save & Restart"
    assert _displayed(view.clear_button) == "Clear all chat history & files"

    view.upload_entry.setText("2")
    view._on_save_settings()
    assert _displayed(view.save_restart_button) == t("gui.savingAndRestarting")

    app.finish_action()
    assert _displayed(view.save_restart_button) == "Save & Restart"


def test_long_english_modal_titles_wrap_inside_the_card(english) -> None:
    theme = current_theme()
    cards = [
        PasswordDialog(theme, t("gui.initPasswordTitle"), t("login.passwordPlaceholder")),
        ClearDataDialog(theme),
    ]
    for card in cards:
        card.adjustSize()
        title = card.title_label
        assert title.wordWrap()
        assert title.width() <= card.width()


def test_window_corners_outside_the_rounded_shell_use_the_theme_background(
    english, qt_application: QApplication, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无边框窗口声明了不透明绘制，圆角外侧像素必须被填充而不是残留未初始化内容。"""
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QColor

    from lanimals.gui import app as app_module

    monkeypatch.setattr(app_module.SystemTray, "start", lambda _tray: None)
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.LANimalsApp(data_dir=tmp_path / "data")
    try:
        window.show()
        qt_application.processEvents()
        image = window.grab().toImage()
        expected = QColor(window.theme.background).rgb()
        right, bottom = image.width() - 1, image.height() - 1
        for x, y in ((0, 0), (right, 0), (0, bottom), (right, bottom)):
            assert image.pixelColor(x, y).rgb() == expected, (x, y)
    finally:
        window._quitting = True
        window.close()
        window.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

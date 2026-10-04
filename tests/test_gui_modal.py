"""主窗口内密码弹窗的行为回归测试。"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QFrame, QWidget

from lanimals.config import load_config
from lanimals.gui.dialogs import ClearDataDialog, InWindowModalOverlay, PasswordDialog
from lanimals.gui.qt_theme import current_theme


PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def qt_application() -> QApplication:
    """为真实 Qt 控件提供一个无窗口系统依赖的事件循环实例。"""
    return QApplication.instance() or QApplication([])


def test_password_card_validates_before_emitting_confirmation(qt_application: QApplication) -> None:
    theme = current_theme()
    dialog = PasswordDialog(theme, "设置密码", "输入密码")
    submitted: list[str] = []
    dialog.submitted.connect(submitted.append)

    dialog.entry.setText("abcdefg")
    dialog._submit()
    assert submitted == []
    assert dialog.error_label.text()

    dialog.entry.setText("abcdefgh")
    dialog._submit()
    assert submitted == ["abcdefgh"]


def test_clear_data_card_stays_in_the_same_modal_system(qt_application: QApplication) -> None:
    theme = current_theme()
    dialog = ClearDataDialog(theme)
    confirmed: list[bool] = []
    dialog.confirmed.connect(lambda: confirmed.append(True))

    dialog.entry.setText("DELETE ALMOST")
    dialog._submit()
    assert confirmed == []
    assert dialog.error_label.text()

    dialog.entry.setText("DELETE ALL")
    dialog._submit()
    assert confirmed == [True]


def test_clear_data_card_runs_the_host_local_action_before_dismissing(
    qt_application: QApplication,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """确认卡片只能经桌面端控制器执行清除，成功后才撤销遮罩。"""
    from lanimals.gui import app as app_module

    cleared: list[bool] = []
    monkeypatch.setattr(app_module.SystemTray, "start", lambda _tray: None)
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    window = app_module.LANimalsApp(data_dir=tmp_path)
    monkeypatch.setattr(window.controller, "clear_all_data", lambda: cleared.append(True))

    def run_synchronously(action, *, on_success=None, on_error=None) -> None:
        try:
            result = action()
        except Exception as error:  # pragma: no cover - 此处保留生产错误分支签名
            if on_error is not None:
                on_error(error)
        else:
            if on_success is not None:
                on_success(result)

    monkeypatch.setattr(window, "run_controller_action", run_synchronously)
    window.show_clear_data_dialog()

    overlay = window._modal_overlay
    assert overlay is not None
    card = overlay.findChild(ClearDataDialog)
    assert card is not None
    card.entry.setText("DELETE ALL")
    card._submit()

    assert cleared == [True]
    assert window._modal_overlay is None
    window._quitting = True
    window.close()
    window.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_password_modal_blurs_only_its_in_window_background(qt_application: QApplication) -> None:
    theme = current_theme()
    host = QWidget()
    host.resize(340, 430)
    background = QFrame(host)
    background.setGeometry(host.rect())
    overlay = InWindowModalOverlay(background, theme, host)
    dialog = PasswordDialog(theme, "设置密码", "输入密码")

    overlay.present(dialog)

    assert overlay.parentWidget() is host
    assert dialog.parentWidget() is overlay
    assert background.graphicsEffect() is overlay.blur_effect
    assert not overlay.isHidden()

    overlay.dismiss()
    assert background.graphicsEffect() is None


def test_password_flows_use_the_in_window_modal_instead_of_a_native_dialog() -> None:
    app_source = (PROJECT_ROOT / "lanimals/gui/app.py").read_text(encoding="utf-8")
    views_source = (PROJECT_ROOT / "lanimals/gui/views.py").read_text(encoding="utf-8")

    assert "InWindowModalOverlay" in app_source
    assert "def _present_modal(" in app_source
    assert "def show_change_password_dialog(" in app_source
    assert "def show_clear_data_dialog(" in app_source
    assert "dialog.exec()" not in app_source
    assert "self.app.show_change_password_dialog()" in views_source
    assert "self.app.show_clear_data_dialog()" in views_source
    assert "class ClearDataDialog(_BaseCard)" in (PROJECT_ROOT / "lanimals/gui/dialogs.py").read_text(encoding="utf-8")


def test_first_password_flow_saves_config_and_starts_from_the_in_window_card(
    qt_application: QApplication,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """首次启动不应另开原生窗口，提交后必须继续走同一个控制器启动服务。"""
    from lanimals.gui import app as app_module
    from lanimals.gui.controller import ServerController

    started: list[bool] = []
    monkeypatch.setattr(app_module.SystemTray, "start", lambda _tray: None)
    monkeypatch.setattr(app_module.QTimer, "singleShot", lambda *_args: None)
    monkeypatch.setattr(ServerController, "start", lambda controller: started.append(True))

    window = app_module.LANimalsApp(data_dir=tmp_path)

    def run_synchronously(action, *, on_success=None, on_error=None) -> None:
        try:
            result = action()
        except Exception as error:  # pragma: no cover - 这里用于保留生产错误分支签名
            if on_error is not None:
                on_error(error)
        else:
            if on_success is not None:
                on_success(result)

    monkeypatch.setattr(window, "run_controller_action", run_synchronously)
    window._check_first_launch_and_start()

    overlay = window._modal_overlay
    assert overlay is not None
    card = overlay.findChild(PasswordDialog)
    assert card is not None

    card.entry.setText("fresh-password")
    card._submit()

    assert load_config(tmp_path).password_hash
    assert started == [True]
    assert window._modal_overlay is None
    window._quitting = True
    window.close()
    window.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

"""主页局域网访问开关的回归测试。"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from lanimals.gui.i18n import t
from lanimals.gui.qt_theme import current_theme
from lanimals.gui.views import MainView
from lanimals.gui.widgets import AnimatedToggle
from tests.test_gui_settings import _QueuedApp


class _LanController:
    def __init__(self, *, fail: bool = False) -> None:
        self.local_only = False
        self.fail = fail
        self.requests: list[bool] = []

    def set_local_only(self, local_only: bool) -> None:
        self.requests.append(local_only)
        if self.fail:
            raise RuntimeError("端口被占用")
        self.local_only = local_only


class _App(_QueuedApp):
    def __init__(self, controller: _LanController) -> None:
        super().__init__()
        self.controller = controller  # type: ignore[assignment]
        self.show_settings = lambda: None
        self.schedule_toast_clear = lambda _label: None


@pytest.fixture(scope="module")
def qt_application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_lan_switch_replaces_the_status_dot_next_to_the_brand(qt_application: QApplication) -> None:
    view = MainView(_App(_LanController()), current_theme())

    assert not hasattr(view, "status_dot")
    assert isinstance(view.lan_switch, AnimatedToggle)
    header = view.layout().itemAt(0).layout()
    widgets = [header.itemAt(index).widget() for index in range(header.count())]
    brand_index = next(i for i, w in enumerate(widgets) if isinstance(w, QLabel) and w.text() == "LANimals")
    assert widgets[brand_index + 1] is view.lan_switch
    assert view.lan_switch.toolTip() == t("gui.lanAccess")
    assert view.lan_switch.accessibleName() == t("gui.lanAccess")


def test_lan_switch_applies_immediately_and_locks_until_restart_finishes(qt_application: QApplication) -> None:
    controller = _LanController()
    app = _App(controller)
    view = MainView(app, current_theme())
    view.update_data("http://192.168.1.20:8787/", True, local_only=False)
    assert view.lan_switch.isChecked()

    view.lan_switch.click()

    assert app._pending is not None
    assert not view.lan_switch.isEnabled()
    # 后台重启过程中到达的状态刷新不能把开关弹回旧值。
    view.update_data("http://192.168.1.20:8787/", True, local_only=False)
    assert not view.lan_switch.isChecked()

    app.finish_action()

    assert controller.requests == [True]
    assert controller.local_only is True
    assert view.lan_switch.isEnabled()
    assert not view.lan_switch.isChecked()


def test_lan_switch_reverts_when_the_restart_fails(qt_application: QApplication) -> None:
    controller = _LanController(fail=True)
    app = _App(controller)
    view = MainView(app, current_theme())
    view.update_data("http://192.168.1.20:8787/", True, local_only=False)

    view.lan_switch.click()
    app.finish_action()

    assert view.lan_switch.isEnabled()
    assert view.lan_switch.isChecked()
    assert view.toast.text() == t("gui.lanAccessFailed")


def test_stopped_service_is_shown_in_place_of_the_qr_code(qt_application: QApplication) -> None:
    view = MainView(_App(_LanController()), current_theme())

    view.update_data("", False, local_only=False)
    assert view.qr_label.text() == t("gui.statusStopped")
    # 停止时不显示刺眼的空白卡片（深色主题下尤其明显），二维码需要的白底只在运行时出现。
    assert "#ffffff" not in view.qr_box.styleSheet()

    view.update_data("http://192.168.1.20:8787/", True, local_only=False)
    assert view.qr_label.text() == ""
    assert view.qr_label.pixmap() is not None and not view.qr_label.pixmap().isNull()
    assert "#ffffff" in view.qr_box.styleSheet()


def test_restart_triggered_by_the_switch_does_not_flash_the_stopped_state(qt_application: QApplication) -> None:
    """切换拨杆会让服务先停后启；这段瞬时的“已停止”不能闪现在主页上。"""
    app = _App(_LanController())
    view = MainView(app, current_theme())
    view.update_data("http://192.168.1.20:8787/", True, local_only=False)

    view.lan_switch.click()
    view.update_data("", False, local_only=True)
    assert view.qr_label.text() != t("gui.statusStopped")

    app.finish_action()
    view.update_data("http://127.0.0.1:8787/", True, local_only=True)
    assert view.qr_label.text() == ""

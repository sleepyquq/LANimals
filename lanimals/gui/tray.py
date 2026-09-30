"""LANimals 跨平台系统托盘管理（Qt 原生 QSystemTrayIcon）。"""

from __future__ import annotations

import logging
import sys
from typing import Callable

from PIL import Image
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from lanimals.gui.i18n import t
from lanimals.gui.theme import load_app_icon_image

logger = logging.getLogger("lanimals.tray")


def create_tray_image(size: int = 64) -> Image.Image:
    """加载与窗口和任务栏完全一致的应用图标。"""
    return load_app_icon_image(size)


def _tray_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 32, 64):
        rgba = create_tray_image(size).convert("RGBA")
        image = QImage(
            rgba.tobytes("raw", "RGBA"), rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888
        ).copy()
        icon.addPixmap(QPixmap.fromImage(image))
    return icon


class SystemTray:
    """在 Qt 主线程运行的系统托盘；Windows、macOS 与 Linux 使用各自的原生实现。"""

    def __init__(
        self,
        on_show: Callable[[], None],
        on_open_browser: Callable[[], None],
        on_toggle_server: Callable[[], None],
        on_exit: Callable[[], None],
    ) -> None:
        self.on_show = on_show
        self.on_open_browser = on_open_browser
        self.on_toggle_server = on_toggle_server
        self.on_exit = on_exit

        self._icon: QSystemTrayIcon | None = None
        self._menu: QMenu | None = None

    @property
    def available(self) -> bool:
        """托盘图标是否真正显示；为 False 时主窗口不能隐藏到托盘。"""
        return self._icon is not None

    def start(self) -> None:
        """在真正需要托盘时才创建原生图标，桌面环境不支持时主窗口仍可用。"""
        try:
            if not QSystemTrayIcon.isSystemTrayAvailable():
                logger.warning("当前桌面环境没有系统托盘，关闭按钮将改为最小化。")
                return
            menu = QMenu()
            menu.addAction(t("gui.trayShow")).triggered.connect(lambda: self.on_show())
            menu.addAction(t("gui.trayOpen")).triggered.connect(lambda: self.on_open_browser())
            menu.addAction(t("gui.trayToggle")).triggered.connect(lambda: self.on_toggle_server())
            menu.addSeparator()
            menu.addAction(t("gui.trayExit")).triggered.connect(lambda: self.stop_and_exit())

            icon = QSystemTrayIcon(_tray_icon())
            icon.setToolTip("LANimals")
            icon.setContextMenu(menu)
            icon.activated.connect(self._on_activated)
            icon.show()
            self._menu = menu
            self._icon = icon
        except Exception as error:
            logger.warning("系统托盘不可用，主窗口将继续运行：%s", error)
            self.stop()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # macOS 单击菜单栏图标时系统会弹出菜单，此时不抢占前台窗口。
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick or (
            reason == QSystemTrayIcon.ActivationReason.Trigger and sys.platform != "darwin"
        ):
            self.on_show()

    def stop_and_exit(self) -> None:
        self.stop()
        self.on_exit()

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.hide()
                self._icon.deleteLater()
            except Exception:
                pass
            self._icon = None
        if self._menu is not None:
            try:
                self._menu.deleteLater()
            except Exception:
                pass
            self._menu = None

"""LANimals 跨平台系统托盘管理。"""

from __future__ import annotations

import logging
import threading
from typing import Callable

from PIL import Image
import pystray

from lanimals.gui.i18n import t
from lanimals.gui.theme import load_app_icon_image

logger = logging.getLogger("lanimals.tray")


def create_tray_image(size: int = 64) -> Image.Image:
    """加载与窗口和任务栏完全一致的应用图标。"""
    return load_app_icon_image(size)


class SystemTray:
    """封装 pystray 系统托盘交互。"""

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

        self._icon: pystray.Icon | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        image = create_tray_image(64)
        menu = pystray.Menu(
            pystray.MenuItem(t("gui.trayShow"), lambda: self.on_show(), default=True),
            pystray.MenuItem(t("gui.trayOpen"), lambda: self.on_open_browser()),
            pystray.MenuItem(t("gui.trayToggle"), lambda: self.on_toggle_server()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(t("gui.trayExit"), lambda: self.stop_and_exit()),
        )
        self._icon = pystray.Icon("lanimals", image, "LANimals", menu)
        self._thread = threading.Thread(target=self._icon.run, daemon=True, name="lanimals-tray")
        self._thread.start()

    def stop_and_exit(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
        self.on_exit()

    def stop(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

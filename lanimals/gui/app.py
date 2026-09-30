"""LANimals 的 Qt 原生桌面控制面板。"""

from __future__ import annotations

import logging
import sys
import threading
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, Qt, Signal, Slot
from PySide6.QtGui import QCloseEvent, QColor, QIcon, QPainter, QPaintEvent, QShowEvent
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QVBoxLayout, QWidget

from lanimals.gui.controller import ServerController
from lanimals.gui.dialogs import ClearDataDialog, InWindowModalOverlay, PasswordDialog
from lanimals.gui.i18n import t
from lanimals.gui.qt_theme import WINDOW_CORNER_RADIUS, QtTheme, current_theme
from lanimals.gui.single_instance import SingleInstanceLock
from lanimals.gui.tray import SystemTray
from lanimals.gui.views import MainView, SettingsView
from lanimals.gui.widgets import DragRegion, HoverToolButton, PageHost


logger = logging.getLogger("lanimals.app")


def native_rounded_corners_available() -> bool:
    """只有 Windows 11（build 22000+）能由 DWM 为无边框窗口裁出原生圆角与阴影。"""
    if sys.platform != "win32":
        return False
    try:
        return sys.getwindowsversion().build >= 22000
    except Exception:
        return False


def _setup_app_logging(data_dir: Path) -> None:
    """初始化 GUI 日志；失败时不影响桌面端启动。"""
    try:
        log_file = data_dir / "lanimals_gui.log"
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
        )
    except Exception:
        pass


class LANimalsApp(QMainWindow):
    """由 Qt 平台层独占窗口生命周期的 LANimals 主窗口。"""

    wake_requested = Signal()
    status_changed = Signal()
    open_browser_requested = Signal()
    toggle_server_requested = Signal()
    quit_requested = Signal()
    controller_action_finished = Signal(int, object, object)

    def __init__(self, data_dir: Path | str = "data", instance_lock: SingleInstanceLock | None = None) -> None:
        self._qt_application = QApplication.instance() or QApplication(sys.argv)
        super().__init__()

        resolved_data_dir = Path(data_dir).expanduser().resolve()
        resolved_data_dir.mkdir(parents=True, exist_ok=True)
        _setup_app_logging(resolved_data_dir)

        self.theme: QtTheme = current_theme()
        self.instance_lock = instance_lock
        self._quitting = False
        self._dwm_configured = False
        self._toast_target: QLabel | None = None
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._clear_toast)
        self._modal_overlay: InWindowModalOverlay | None = None
        self._next_action_id = 0
        self._action_callbacks: dict[
            int,
            tuple[Callable[[Any], None] | None, Callable[[Exception], None] | None],
        ] = {}

        # Qt 在创建时就拥有无边框标志；绝不在运行中修改 Win32 窗口样式。
        self.setWindowTitle("LANimals")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(340, 430)
        # 圆角方案必须在窗口首次显示前确定，运行中不再切换窗口属性。
        self._native_rounded_corners = native_rounded_corners_available()
        if self._native_rounded_corners:
            # Windows 11：不透明窗口 + DWM 原生圆角与阴影。
            self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
            self.setStyleSheet(f"QMainWindow {{ background: {self.theme.background}; }}")
        else:
            # 其他平台：透明顶层窗口，由圆角外壳自行绘制抗锯齿圆角。
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setStyleSheet("QMainWindow { background: transparent; }")
        self._setup_window_icon()
        self._set_windows_app_identity()

        self.controller = ServerController(data_dir=resolved_data_dir)
        self.controller.add_status_listener(self._on_server_status_changed)

        self._build_ui()
        self._connect_cross_thread_events()

        if self.instance_lock:
            self.instance_lock.on_wakeup = self.show_window

        self.tray = SystemTray(
            on_show=self.show_window,
            on_open_browser=self._tray_open_browser,
            on_toggle_server=self._tray_toggle_server,
            on_exit=self.quit_app,
        )
        self.tray.start()

        # 先完整构造、绘制并显示 Qt 内容，再延后启动本地服务。
        QTimer.singleShot(250, self._check_first_launch_and_start)

    def _setup_window_icon(self) -> None:
        icon_path = Path(__file__).resolve().parent / "assets" / "icon.ico"
        if icon_path.exists():
            icon = QIcon(str(icon_path))
            self.setWindowIcon(icon)
            self._qt_application.setWindowIcon(icon)

    def _set_windows_app_identity(self) -> None:
        """仅设置任务栏归属图标，不修改窗口样式或非客户区。"""
        if sys.platform != "win32":
            return
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("com.sleepyquq.LANimals")
        except Exception as error:
            logger.debug("设置 Windows AppUserModelID 失败: %s", error)

    def _build_ui(self) -> None:
        shell = QFrame(self)
        shell.setObjectName("lanimals-shell")
        shell.setStyleSheet(
            f"""
            QFrame#lanimals-shell {{
                background: {self.theme.background};
                border: 1px solid {self.theme.card_border};
                border-radius: {WINDOW_CORNER_RADIUS}px;
            }}
            """
        )
        self.setCentralWidget(shell)

        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        # 内容层和模态层互为兄弟控件；虚化时只作用于内容层，不会影响密码卡片。
        self.content_layer = QWidget(shell)
        shell_layout.addWidget(self.content_layer)
        layout = QVBoxLayout(self.content_layer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.top_bar = DragRegion(self, self.content_layer)
        self.top_bar.setFixedHeight(36)
        self.top_bar.setStyleSheet("background: transparent;")
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(12, 6, 12, 4)
        top_layout.setSpacing(0)

        self.page_header = QWidget(self.top_bar)
        self.page_header_layout = QHBoxLayout(self.page_header)
        self.page_header_layout.setContentsMargins(0, 0, 0, 0)
        self.page_header_layout.setSpacing(6)
        top_layout.addWidget(self.page_header, 1)

        self.minimize_button = HoverToolButton("−", "", self.theme, parent=self.top_bar)
        self.minimize_button.clicked.connect(self.minimize_to_taskbar)
        self.close_button = HoverToolButton("×", "", self.theme, danger=True, parent=self.top_bar)
        self.close_button.clicked.connect(self.hide_to_tray)
        top_layout.addWidget(self.minimize_button)
        top_layout.addSpacing(2)
        top_layout.addWidget(self.close_button)
        layout.addWidget(self.top_bar)

        self.page_host = PageHost(self.content_layer)
        layout.addWidget(self.page_host, 1)
        self.main_view = MainView(self, self.theme, self.page_host)
        self.settings_view = SettingsView(self, self.theme, self.page_host)
        self.page_host.add_page("main", self.main_view)
        self.page_host.add_page("settings", self.settings_view)
        self.show_main(initial=True)

    def _connect_cross_thread_events(self) -> None:
        self.wake_requested.connect(self._restore_window)
        self.status_changed.connect(self._handle_status_update)
        self.open_browser_requested.connect(self._open_browser)
        self.toggle_server_requested.connect(self._toggle_server)
        self.quit_requested.connect(self._do_quit)
        self.controller_action_finished.connect(self._finish_controller_action)

    def _clear_page_header(self) -> None:
        while self.page_header_layout.count():
            item = self.page_header_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.page_header_layout.addStretch(1)

    def _show_settings_header(self) -> None:
        while self.page_header_layout.count():
            item = self.page_header_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        back = HoverToolButton("←", "", self.theme, parent=self.page_header)
        back.clicked.connect(self.show_main)
        title = QLabel(t("gui.settingsTitle"), self.page_header)
        title.setStyleSheet(f"color: {self.theme.text_main}; font-size: 14px; font-weight: 600;")
        self.page_header_layout.addWidget(back)
        self.page_header_layout.addWidget(title)
        self.page_header_layout.addStretch(1)

    def show_main(self, initial: bool = False) -> None:
        self._clear_page_header()
        self._update_main_view()
        self.page_host.show_page("main", direction=-1 if not initial else 0)

    def show_settings(self) -> None:
        self._show_settings_header()
        self.settings_view.refresh_settings()
        self.page_host.show_page("settings", direction=1)

    def _update_main_view(self) -> None:
        self.main_view.update_data(
            join_url=self.controller.join_url,
            is_running=self.controller.is_running,
            local_only=self.controller.local_only,
        )

    def _check_first_launch_and_start(self) -> None:
        if not self.controller.has_config():
            self._show_initial_password_dialog()
            return
        self.run_controller_action(self.controller.start)

    def _present_modal(self, card: QWidget) -> InWindowModalOverlay:
        """在当前主窗口内显示卡片，不创建额外的原生窗口。"""
        if self._modal_overlay is not None:
            self._dismiss_modal(self._modal_overlay)
        overlay = InWindowModalOverlay(self.content_layer, self.theme, self.centralWidget())
        self._modal_overlay = overlay
        overlay.present(card)
        return overlay

    def _dismiss_modal(self, overlay: InWindowModalOverlay | None = None) -> None:
        target = overlay or self._modal_overlay
        if target is None:
            return
        target.dismiss()
        if target is self._modal_overlay:
            self._modal_overlay = None

    def _show_initial_password_dialog(self) -> None:
        dialog = PasswordDialog(
            self.theme,
            t("gui.initPasswordTitle"),
            t("login.passwordPlaceholder"),
            hint=t("gui.initPasswordHint"),
        )
        overlay = self._present_modal(dialog)
        dialog.cancelled.connect(lambda: self._dismiss_modal(overlay))
        dialog.submitted.connect(lambda password: self._save_initial_password(dialog, overlay, password))
        dialog.entry.setFocus()

    def _save_initial_password(
        self,
        dialog: PasswordDialog,
        overlay: InWindowModalOverlay,
        password: str,
    ) -> None:
        dialog.set_pending(True)
        self.run_controller_action(
            lambda: self.controller.init_config_with_password(password),
            on_success=lambda _result: self._start_after_initial_password(overlay),
            on_error=lambda error: dialog.show_error(str(error)),
        )

    def _start_after_initial_password(self, overlay: InWindowModalOverlay) -> None:
        self._dismiss_modal(overlay)
        self.run_controller_action(self.controller.start)

    def show_change_password_dialog(self) -> None:
        """从设置页打开主窗口内的改密码卡片。"""
        dialog = PasswordDialog(
            self.theme,
            t("gui.changePassword"),
            t("gui.newPasswordPlaceholder"),
        )
        overlay = self._present_modal(dialog)
        dialog.cancelled.connect(lambda: self._dismiss_modal(overlay))
        dialog.submitted.connect(lambda password: self._save_changed_password(dialog, overlay, password))
        dialog.entry.setFocus()

    def _save_changed_password(
        self,
        dialog: PasswordDialog,
        overlay: InWindowModalOverlay,
        password: str,
    ) -> None:
        dialog.set_pending(True)
        self.run_controller_action(
            lambda: self.controller.update_password(password),
            on_success=lambda _result: self._finish_password_change(overlay),
            on_error=lambda error: dialog.show_error(str(error)),
        )

    def _finish_password_change(self, overlay: InWindowModalOverlay) -> None:
        self._dismiss_modal(overlay)
        self.main_view.toast.setText(t("gui.passwordChanged"))
        self.schedule_toast_clear(self.main_view.toast)

    def show_clear_data_dialog(self) -> None:
        """在主窗口内显示清除记录确认卡片。"""
        dialog = ClearDataDialog(self.theme)
        overlay = self._present_modal(dialog)
        dialog.cancelled.connect(lambda: self._dismiss_modal(overlay))
        dialog.confirmed.connect(lambda: self._clear_all_data(dialog, overlay))
        dialog.entry.setFocus()

    def _clear_all_data(self, dialog: ClearDataDialog, overlay: InWindowModalOverlay) -> None:
        dialog.set_pending(True)
        self.run_controller_action(
            self.controller.clear_all_data,
            on_success=lambda _result: self._finish_clear_data(overlay),
            on_error=lambda _error: dialog.show_error(t("gui.clearDataFailed")),
        )

    def _finish_clear_data(self, overlay: InWindowModalOverlay) -> None:
        self._dismiss_modal(overlay)
        self.main_view.toast.setText(t("gui.clearSuccess"))
        self.schedule_toast_clear(self.main_view.toast)

    def _on_server_status_changed(self, status: str, detail: str | None = None) -> None:
        """控制器可能在后台线程回调，借由 Qt 信号回到 GUI 线程。"""
        self.status_changed.emit()

    @Slot()
    def _handle_status_update(self) -> None:
        self._update_main_view()
        if self.page_host._current_name == "settings":
            self.settings_view.refresh_settings()

    def schedule_toast_clear(self, label: QLabel) -> None:
        self._toast_target = label
        self._toast_timer.start(2_500)

    @Slot()
    def _clear_toast(self) -> None:
        if self._toast_target is not None:
            self._toast_target.clear()
            self._toast_target = None

    def run_controller_action(
        self,
        action: Callable[[], Any],
        *,
        on_success: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """将可能重启服务的本地管理操作移出 Qt 事件循环。"""
        action_id = self._next_action_id
        self._next_action_id += 1
        self._action_callbacks[action_id] = (on_success, on_error)

        def runner() -> None:
            try:
                result = action()
            except Exception as error:
                logger.exception("执行主机本地管理操作失败: %s", error)
                self.controller_action_finished.emit(action_id, None, error)
            else:
                self.controller_action_finished.emit(action_id, result, None)

        threading.Thread(target=runner, daemon=True, name="lanimals-gui-action").start()

    @Slot(int, object, object)
    def _finish_controller_action(self, action_id: int, result: Any, error: Exception | None) -> None:
        on_success, on_error = self._action_callbacks.pop(action_id, (None, None))
        if error is not None:
            if on_error is not None:
                on_error(error)
            return
        if on_success is not None:
            on_success(result)

    def show_window(self) -> None:
        """可由托盘/单实例 IPC 的任意线程安全唤醒。"""
        self.wake_requested.emit()

    @Slot()
    def _restore_window(self) -> None:
        # 不改变透明度、样式、大小或置顶层级，避免任务栏恢复后再闪一次。
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def minimize_to_taskbar(self) -> None:
        """交给 Qt/Windows 平台插件执行完整原生最小化与恢复协议。"""
        self.showMinimized()

    def hide_to_tray(self) -> None:
        """关闭按钮只隐藏至托盘，不暴露远程管理操作。"""
        self.hide()

    def _tray_open_browser(self) -> None:
        self.open_browser_requested.emit()

    @Slot()
    def _open_browser(self) -> None:
        if self.controller.join_url:
            webbrowser.open(self.controller.join_url)

    def _tray_toggle_server(self) -> None:
        self.toggle_server_requested.emit()

    @Slot()
    def _toggle_server(self) -> None:
        if self.controller.is_running:
            self.run_controller_action(self.controller.stop)
        else:
            self.run_controller_action(self.controller.start)

    def quit_app(self) -> None:
        self.quit_requested.emit()

    @Slot()
    def _do_quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        try:
            self.tray.stop()
        except Exception:
            pass
        try:
            self.controller.stop()
        except Exception:
            pass
        if self.instance_lock:
            try:
                self.instance_lock.release()
            except Exception:
                pass
        self.close()
        self._qt_application.quit()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API 命名
        if self._quitting:
            event.accept()
            return
        event.ignore()
        self.hide_to_tray()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 - Qt API 命名
        if not self._native_rounded_corners:
            return
        # WA_OpaquePaintEvent 要求自行铺满整个窗口；否则外壳圆角外侧会残留未初始化像素，
        # 这些像素随后由 DWM 圆角裁掉。
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor(self.theme.background))
        painter.end()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt API 命名
        super().showEvent(event)
        if not self._dwm_configured:
            self._dwm_configured = True
            QTimer.singleShot(0, self._configure_windows_dwm)

    def _configure_windows_dwm(self) -> None:
        """仅请求 Windows 11 原生圆角/深色适配，不触碰窗口边框样式。"""
        if not self._native_rounded_corners:
            return
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = wintypes.HWND(int(self.winId()))
            dwmapi = ctypes.WinDLL("dwmapi")
            dark_mode = ctypes.c_int(1 if self.theme.is_dark else 0)
            rounded = ctypes.c_int(2)
            dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
            dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(rounded), ctypes.sizeof(rounded))
        except Exception as error:
            logger.debug("配置 Windows DWM 外观失败: %s", error)

    def mainloop(self) -> int:
        """保持旧入口兼容，同时使用 Qt 事件循环。"""
        self.show()
        return self._qt_application.exec()

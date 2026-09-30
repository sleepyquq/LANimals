"""LANimals Qt 主页与固定设置页。"""

from __future__ import annotations

import logging
import webbrowser
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QFont, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QApplication,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lanimals.config import parse_size
from lanimals.gui.i18n import button_text, t
from lanimals.gui.qt_theme import QtTheme
from lanimals.gui.theme import create_gear_image, load_app_icon_image
from lanimals.gui.widgets import AnimatedToggle, ClickableLabel, WarmComboBox
from lanimals.network import qr_pil_image

if TYPE_CHECKING:
    from lanimals.gui.app import LANimalsApp


logger = logging.getLogger("lanimals.views")


def _pixmap_from_pil(image) -> QPixmap:
    """复制像素数据，避免 Qt 图像继续引用会被回收的 Pillow 缓冲区。"""
    rgba = image.convert("RGBA")
    qimage = QImage(
        rgba.tobytes("raw", "RGBA"),
        rgba.width,
        rgba.height,
        rgba.width * 4,
        QImage.Format.Format_RGBA8888,
    ).copy()
    return QPixmap.fromImage(qimage)


def _card_style(theme: QtTheme) -> str:
    # 限定到卡片自身，不能把背景/边框样式继承给内部文字和输入控件。
    return f"""
        QFrame#settings-card {{
            background: {theme.card};
            border: 1px solid {theme.card_border};
            border-radius: 10px;
        }}
    """


def _settings_field_label(text: str, parent: QWidget, theme: QtTheme) -> QLabel:
    """创建设置项标题，避免字段标签和页面标题争夺视觉层级。"""
    label = QLabel(text, parent)
    label.setFont(QFont("Microsoft YaHei UI", 10, QFont.Weight.Medium))
    label.setStyleSheet(f"color: {theme.text_main};")
    return label


def _button_style(theme: QtTheme, background: str, hover: str, text: str) -> str:
    return f"""
        QPushButton {{
            background: {background};
            border: none;
            border-radius: 8px;
            color: {text};
            min-height: 34px;
            font-size: 12px;
            font-weight: 600;
        }}
        QPushButton:hover {{ background: {hover}; }}
        QPushButton:pressed {{ background: {hover}; }}
    """


class MainView(QWidget):
    """扫码主页：保留地址、二维码和设置入口，窗口本身不参与任何显隐动画。"""

    def __init__(self, app: LANimalsApp, theme: QtTheme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.theme = theme
        self._current_url = ""
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 6, 20, 20)
        layout.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(8)
        cat_icon = QLabel(self)
        cat_icon.setPixmap(_pixmap_from_pil(load_app_icon_image(28)))
        cat_icon.setFixedSize(28, 28)
        header.addWidget(cat_icon)

        brand = QLabel("LANimals", self)
        brand.setFont(QFont("Microsoft YaHei UI", 15, QFont.Weight.DemiBold))
        brand.setStyleSheet(f"color: {self.theme.text_main};")
        header.addWidget(brand)

        self.status_dot = QLabel(self)
        self.status_dot.setFixedSize(10, 10)
        self._set_status_dot(False)
        header.addWidget(self.status_dot)
        header.addStretch(1)
        layout.addLayout(header)

        layout.addStretch(1)
        self.qr_box = QFrame(self)
        self.qr_box.setFixedSize(184, 184)
        self.qr_box.setStyleSheet("background: #ffffff; border: none; border-radius: 12px;")
        qr_layout = QVBoxLayout(self.qr_box)
        qr_layout.setContentsMargins(8, 8, 8, 8)
        self.qr_label = QLabel(self.qr_box)
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setStyleSheet("background: transparent;")
        qr_layout.addWidget(self.qr_label)
        layout.addWidget(self.qr_box, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)

        link_row = QHBoxLayout()
        link_row.setSpacing(6)
        self.link_label = ClickableLabel(self)
        self.link_label.setFont(QFont("Consolas", 10))
        self.link_label.setStyleSheet(f"color: {self.theme.link};")
        self.link_label.setText("http://127.0.0.1:8787/")
        self.link_label.clicked.connect(self._on_link_click)
        self.link_label.installEventFilter(self)
        link_row.addWidget(self.link_label)

        gear = QToolButton(self)
        gear.setIcon(QIcon(_pixmap_from_pil(create_gear_image(16, color=self.theme.text_muted))))
        gear.setIconSize(gear.iconSize())
        gear.setToolTip(t("gui.settingsTitle"))
        gear.setCursor(Qt.CursorShape.PointingHandCursor)
        gear.setFixedSize(24, 24)
        gear.setStyleSheet(
            f"""
            QToolButton {{ border: none; background: transparent; border-radius: 6px; }}
            QToolButton:hover {{ background: {self.theme.top_control_hover}; }}
            """
        )
        gear.clicked.connect(self.app.show_settings)
        link_row.addWidget(gear)
        link_row_widget = QWidget(self)
        link_row_widget.setLayout(link_row)
        layout.addWidget(link_row_widget, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.toast = QLabel("", self)
        self.toast.setMinimumHeight(16)
        self.toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toast.setStyleSheet(f"color: {self.theme.text_subtle}; font-size: 10px;")
        layout.addWidget(self.toast)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API 命名
        if watched is self.link_label:
            if event.type() == QEvent.Type.Enter:
                self.link_label.setStyleSheet(f"color: {self.theme.link_hover};")
            elif event.type() == QEvent.Type.Leave:
                self.link_label.setStyleSheet(f"color: {self.theme.link};")
        return super().eventFilter(watched, event)

    def _set_status_dot(self, is_running: bool) -> None:
        color = self.theme.status_green if is_running else self.theme.status_gray
        self.status_dot.setStyleSheet(f"background: {color}; border: none; border-radius: 5px;")

    def update_data(self, join_url: str, is_running: bool, local_only: bool = False) -> None:
        self._current_url = join_url
        self._set_status_dot(is_running)
        self.link_label.setText(join_url or "http://127.0.0.1:8787/")
        if join_url:
            self._render_qr_code(join_url)
        else:
            self.qr_label.clear()

    def _render_qr_code(self, url: str) -> None:
        try:
            image = qr_pil_image(url, scale=4, border=1)
            self.qr_label.setPixmap(_pixmap_from_pil(image).scaled(
                168,
                168,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))
        except Exception as error:
            logger.warning("生成二维码失败: %s", error)
            self.qr_label.setText(t("errors.invalidResponse"))
            self.qr_label.setStyleSheet(f"color: {self.theme.text_muted}; font-size: 11px;")

    def _on_link_click(self) -> None:
        if not self._current_url:
            return
        try:
            webbrowser.open(self._current_url)
            clipboard = QApplication.clipboard()
            if clipboard is not None:
                clipboard.setText(self._current_url)
            self.toast.setText(t("gui.copied"))
            self.app.schedule_toast_clear(self.toast)
        except Exception as error:
            logger.debug("打开或复制访问地址失败: %s", error)


class SettingsView(QWidget):
    """固定高度设置页：不含滚动容器，所有控件在单页内完整呈现。"""

    def __init__(self, app: LANimalsApp, theme: QtTheme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.app = app
        self.theme = theme
        self._adapter_map: dict[str, str | None] = {}
        self._refreshing = False
        self._has_unsaved_changes = False
        self._save_pending = False
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 16)
        layout.setSpacing(0)

        net_card = QFrame(self)
        net_card.setObjectName("settings-card")
        net_card.setStyleSheet(_card_style(self.theme))
        net_layout = QVBoxLayout(net_card)
        net_layout.setContentsMargins(16, 14, 16, 14)
        net_layout.setSpacing(0)

        access_row = QHBoxLayout()
        access_row.setSpacing(8)
        lan_label = _settings_field_label(t("gui.lanAccess"), net_card, self.theme)
        access_row.addWidget(lan_label)
        self.lan_switch = AnimatedToggle(self.theme, net_card)
        self.lan_switch.toggled.connect(self._on_lan_access_toggle)
        access_row.addWidget(self.lan_switch)
        access_row.addStretch(1)
        net_layout.addLayout(access_row)
        net_layout.addSpacing(12)

        adapter_label = _settings_field_label(t("gui.networkAdapter"), net_card, self.theme)
        net_layout.addWidget(adapter_label)
        net_layout.addSpacing(6)

        self.adapter_menu = WarmComboBox(self.theme, net_card)
        self.adapter_menu.setFixedHeight(34)
        self.adapter_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self.adapter_menu.setStyleSheet(
            f"""
            QComboBox {{
                background: {self.theme.entry_background};
                border: 1px solid {self.theme.entry_border};
                border-radius: 8px;
                color: {self.theme.text_main};
                padding: 0 10px;
            }}
            QComboBox:hover {{ border-color: {self.theme.secondary_hover}; }}
            QComboBox::drop-down {{
                border: none;
                width: 28px;
                background: {self.theme.secondary_button};
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
            }}
            QComboBox QAbstractItemView {{
                background: {self.theme.card};
                border: 1px solid {self.theme.card_border};
                color: {self.theme.text_main};
                selection-background-color: {self.theme.secondary_hover};
                outline: none;
            }}
            """
        )
        self.adapter_menu.currentTextChanged.connect(self._on_adapter_selected)
        net_layout.addWidget(self.adapter_menu)
        layout.addWidget(net_card)
        layout.addSpacing(12)

        security_card = QFrame(self)
        security_card.setObjectName("settings-card")
        security_card.setStyleSheet(_card_style(self.theme))
        security_layout = QVBoxLayout(security_card)
        security_layout.setContentsMargins(16, 14, 16, 14)
        security_layout.setSpacing(0)

        upload_label = _settings_field_label(t("gui.maxUploadSize"), security_card, self.theme)
        security_layout.addWidget(upload_label)
        security_layout.addSpacing(6)

        self.upload_entry = QLineEdit(security_card)
        self.upload_entry.setPlaceholderText("2")
        self.upload_entry.setFixedHeight(34)
        self.upload_entry.textChanged.connect(self._on_setting_edited)
        security_layout.addWidget(self.upload_entry)
        security_layout.addSpacing(2)

        self.upload_error_label = QLabel("", security_card)
        self.upload_error_label.setMinimumHeight(14)
        self.upload_error_label.setStyleSheet(f"color: {self.theme.danger}; font-size: 10px;")
        security_layout.addWidget(self.upload_error_label)
        security_layout.addSpacing(8)

        self.password_button = QPushButton(button_text("gui.changePassword"), security_card)
        self.password_button.setStyleSheet(
            _button_style(
                self.theme,
                self.theme.secondary_button,
                self.theme.secondary_hover,
                self.theme.secondary_text,
            )
        )
        self.password_button.clicked.connect(self._on_change_password)
        security_layout.addWidget(self.password_button)
        layout.addWidget(security_card)
        layout.addSpacing(8)

        self.save_restart_button = QPushButton(button_text("gui.saveAndRestart"), self)
        self.save_restart_button.setStyleSheet(
            _button_style(self.theme, self.theme.accent, self.theme.accent_hover, "#ffffff")
        )
        self.save_restart_button.clicked.connect(self._on_save_settings)
        layout.addWidget(self.save_restart_button)
        layout.addSpacing(8)

        self.clear_button = QPushButton(button_text("gui.clearData"), self)
        self.clear_button.setStyleSheet(_button_style(self.theme, self.theme.danger, self.theme.danger_hover, "#ffffff"))
        self.clear_button.clicked.connect(self._on_clear_data)
        layout.addWidget(self.clear_button)
        layout.addStretch(1)

    def refresh_settings(self, *, force: bool = False) -> None:
        """用已保存的控制器状态刷新表单，不覆盖用户尚未保存的草稿。"""
        if self._has_unsaved_changes and not force:
            return
        self._refreshing = True
        try:
            self.lan_switch.set_state(not self.app.controller.local_only, animated=False, emit=False)
            try:
                size = self.app.controller.get_max_upload_size()
                gb_value = parse_size(size) / (1024 * 1024 * 1024)
                self.upload_entry.setText(f"{gb_value:g}")
                self.upload_error_label.clear()
            except Exception as error:
                logger.debug("读取上传上限失败: %s", error)

            auto_text = t("gui.autoDetect")
            self._adapter_map = {auto_text: None}
            choices = [auto_text]
            for adapter, ip_address in self.app.controller.get_lan_candidates():
                label = f"{adapter} ({ip_address})"
                self._adapter_map[label] = adapter
                choices.append(label)

            self.adapter_menu.blockSignals(True)
            self.adapter_menu.clear()
            self.adapter_menu.addItems(choices)
            selected = next(
                (label for label, adapter in self._adapter_map.items() if adapter == self.app.controller.selected_adapter),
                auto_text,
            )
            self.adapter_menu.setCurrentText(selected)
            self.adapter_menu.blockSignals(False)
            self._has_unsaved_changes = False
            self._set_settings_controls_enabled(not self._save_pending)
        finally:
            self._refreshing = False

    def _on_lan_access_toggle(self, is_lan_on: bool) -> None:
        if self._refreshing or self._save_pending:
            return
        self.adapter_menu.setEnabled(is_lan_on)
        self._mark_settings_dirty()

    def _on_adapter_selected(self, choice: str) -> None:
        if self._refreshing or self._save_pending:
            return
        self._mark_settings_dirty()

    def _on_setting_edited(self, _value: str) -> None:
        if self._refreshing or self._save_pending:
            return
        self.upload_error_label.clear()
        self._mark_settings_dirty()

    def _mark_settings_dirty(self) -> None:
        self._has_unsaved_changes = True

    def _set_settings_controls_enabled(self, enabled: bool) -> None:
        """保存/重启期间冻结所有会影响同一份主机配置的字段。"""
        self.lan_switch.setEnabled(enabled)
        self.adapter_menu.setEnabled(enabled and self.lan_switch.isChecked())
        self.upload_entry.setEnabled(enabled)
        self.save_restart_button.setEnabled(enabled)

    def _on_save_settings(self) -> None:
        if self._refreshing or self._save_pending:
            return
        value = self.upload_entry.text().strip()
        try:
            number = float(value)
        except ValueError:
            self.upload_error_label.setText(t("gui.maxUploadSizeInvalid"))
            return
        if not 0.1 <= number <= 512:
            self.upload_error_label.setText(t("gui.maxUploadSizeInvalid"))
            return

        self._save_pending = True
        self._set_settings_controls_enabled(False)
        self.save_restart_button.setText(button_text("gui.savingAndRestarting"))
        adapter_name = self._adapter_map.get(self.adapter_menu.currentText())
        self.app.run_controller_action(
            lambda: self.app.controller.apply_settings(
                local_only=not self.lan_switch.isChecked(),
                adapter_name=adapter_name,
                max_upload_size=f"{number:g}GB",
            ),
            on_success=self._finish_settings_save,
            on_error=self._handle_settings_save_error,
        )

    def _finish_settings_save(self, _saved_size: str) -> None:
        self._save_pending = False
        self.save_restart_button.setText(button_text("gui.saveAndRestart"))
        self.refresh_settings(force=True)

    def _handle_settings_save_error(self, error: Exception) -> None:
        self._save_pending = False
        logger.warning("保存并重启设置失败: %s", error)
        self.save_restart_button.setText(button_text("gui.saveAndRestart"))
        self.upload_error_label.setText(t("gui.settingsSaveFailed"))
        self._set_settings_controls_enabled(True)

    def _on_change_password(self) -> None:
        self.app.show_change_password_dialog()

    def _on_clear_data(self) -> None:
        self.app.show_clear_data_dialog()

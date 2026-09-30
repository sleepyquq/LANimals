"""LANimals Qt 的本地管理确认对话框。"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsBlurEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from lanimals.gui.i18n import button_text, t
from lanimals.gui.qt_theme import WINDOW_CORNER_RADIUS, QtTheme, ui_font


def _button_style(theme: QtTheme, background: str, hover: str, text_color: str) -> str:
    return f"""
        QPushButton {{
            background: {background};
            border: none;
            border-radius: 8px;
            color: {text_color};
            font-weight: 600;
            min-height: 36px;
            padding: 0 12px;
        }}
        QPushButton:hover {{ background: {hover}; }}
        QPushButton:pressed {{ background: {hover}; }}
    """


class InWindowModalOverlay(QWidget):
    """覆盖在现有窗口内容上的模态层，只虚化其下方的应用内容。"""

    def __init__(self, background: QWidget, theme: QtTheme, parent: QWidget) -> None:
        super().__init__(parent)
        self._background = background
        self._theme = theme
        self._card: QWidget | None = None
        self._blur_effect = QGraphicsBlurEffect(background)
        self._blur_effect.setBlurRadius(9.0)
        self._blur_effect.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setGeometry(parent.rect())
        parent.installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(0)
        layout.addStretch(1)
        layout.addStretch(1)
        self._layout = layout

    @property
    def blur_effect(self) -> QGraphicsBlurEffect:
        """供调用方和测试确认背景仅使用该虚化效果。"""
        return self._blur_effect

    def present(self, card: QWidget) -> None:
        """将卡片置于当前窗口中央，并阻断其下方内容的输入。"""
        if self._card is not None:
            raise RuntimeError("模态层一次只能显示一个卡片")
        self._card = card
        card.setParent(self)
        self._layout.insertWidget(1, card, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._background.setGraphicsEffect(self._blur_effect)
        self.show()
        self.raise_()
        card.show()
        card.raise_()

    def dismiss(self) -> None:
        """关闭模态层后立刻撤销背景虚化，避免影响后续页面绘制。"""
        parent = self.parentWidget()
        if parent is not None:
            parent.removeEventFilter(self)
        if self._background.graphicsEffect() is not None:
            self._background.setGraphicsEffect(None)
        self.hide()
        self.deleteLater()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API 命名
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.setGeometry(watched.rect())
        return super().eventFilter(watched, event)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API 命名
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scrim = QColor(10, 8, 6, 104) if self._theme.is_dark else QColor(76, 58, 41, 66)
        # 遮罩跟随窗口外壳圆角，透明窗口的四角不会出现方形暗角。
        path = QPainterPath()
        path.addRoundedRect(self.rect(), WINDOW_CORNER_RADIUS, WINDOW_CORNER_RADIUS)
        painter.fillPath(path, scrim)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API 命名
        # 吞掉遮罩上的点击，使背景控件保持真正的模态状态。
        event.accept()


class _BaseCard(QFrame):
    """窗口内悬浮卡片的共用视觉与布局。"""

    def __init__(self, theme: QtTheme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.theme = theme
        self.setObjectName("lanimals-modal-card")
        self.setFixedWidth(286)
        self.setStyleSheet(
            f"""
            QFrame#lanimals-modal-card {{
                background: {theme.card};
                border: 1px solid {theme.card_border};
                border-radius: 12px;
            }}
            QLabel {{ color: {theme.text_main}; }}
            QLineEdit {{
                background: {theme.entry_background};
                border: 1px solid {theme.entry_border};
                border-radius: 8px;
                color: {theme.text_main};
                min-height: 34px;
                padding: 0 10px;
            }}
            QLineEdit:focus {{ border-color: {theme.accent}; }}
            """
        )

    def _layout(self) -> QVBoxLayout:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(8)
        return layout

    def _title(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setFont(ui_font(14, QFont.Weight.DemiBold))
        label.setWordWrap(True)
        self.title_label = label
        return label


class PasswordDialog(_BaseCard):
    """首次设置或变更群聊密码的主窗口内悬浮卡片。"""

    submitted = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        theme: QtTheme,
        title: str,
        placeholder: str,
        *,
        hint: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(theme, parent)
        self.password = ""
        layout = self._layout()
        layout.addWidget(self._title(title))
        if hint:
            hint_label = QLabel(hint, self)
            hint_label.setWordWrap(True)
            hint_label.setStyleSheet(f"color: {theme.text_muted}; font-size: 11px;")
            layout.addWidget(hint_label)

        self.entry = QLineEdit(self)
        self.entry.setPlaceholderText(placeholder)
        self.entry.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.entry)

        self.error_label = QLabel("", self)
        self.error_label.setMinimumHeight(14)
        self.error_label.setStyleSheet(f"color: {theme.danger}; font-size: 11px;")
        layout.addWidget(self.error_label)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.cancel_button = QPushButton(button_text("gui.cancel"), self)
        self.cancel_button.setStyleSheet(_button_style(theme, theme.secondary_button, theme.secondary_hover, theme.secondary_text))
        self.cancel_button.clicked.connect(self.cancelled.emit)
        self.confirm_button = QPushButton(button_text("gui.confirm"), self)
        self.confirm_button.setStyleSheet(_button_style(theme, theme.accent, theme.accent_hover, "#ffffff"))
        self.confirm_button.clicked.connect(self._submit)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.confirm_button)
        layout.addLayout(actions)
        self.entry.returnPressed.connect(self._submit)
        self.entry.setFocus()

    def _submit(self) -> None:
        value = self.entry.text().strip()
        if not value:
            self.error_label.setText(t("gui.passwordEmpty"))
            return
        if len(value) < 4:
            self.error_label.setText(t("gui.passwordTooShort"))
            return
        self.password = value
        self.error_label.clear()
        self.submitted.emit(value)

    def set_pending(self, pending: bool) -> None:
        """提交时锁定卡片，避免并发写入配置。"""
        self.entry.setEnabled(not pending)
        self.cancel_button.setEnabled(not pending)
        self.confirm_button.setEnabled(not pending)

    def show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.set_pending(False)


class ClearDataDialog(_BaseCard):
    """要求精确输入 DELETE ALL 的窗口内高风险确认卡片。"""

    confirmed = Signal()
    cancelled = Signal()

    def __init__(self, theme: QtTheme, parent: QWidget | None = None) -> None:
        super().__init__(theme, parent)
        layout = self._layout()
        title = self._title(t("gui.clearData"))
        title.setStyleSheet(f"color: {theme.danger};")
        layout.addWidget(title)

        warning = QLabel(t("gui.clearDataWarning"), self)
        warning.setWordWrap(True)
        warning.setStyleSheet(f"color: {theme.text_muted}; font-size: 11px;")
        layout.addWidget(warning)

        prompt = QLabel(t("gui.clearConfirmPrompt"), self)
        prompt.setWordWrap(True)
        prompt.setStyleSheet(f"color: {theme.text_main}; font-size: 11px;")
        layout.addWidget(prompt)

        self.entry = QLineEdit(self)
        self.entry.setPlaceholderText("DELETE ALL")
        layout.addWidget(self.entry)

        self.error_label = QLabel("", self)
        self.error_label.setMinimumHeight(14)
        self.error_label.setStyleSheet(f"color: {theme.danger}; font-size: 11px;")
        layout.addWidget(self.error_label)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.cancel_button = QPushButton(button_text("gui.cancel"), self)
        self.cancel_button.setStyleSheet(
            _button_style(theme, theme.secondary_button, theme.secondary_hover, theme.secondary_text)
        )
        self.cancel_button.clicked.connect(self.cancelled.emit)
        self.confirm_button = QPushButton(button_text("gui.confirm"), self)
        self.confirm_button.setStyleSheet(_button_style(theme, theme.danger, theme.danger_hover, "#ffffff"))
        self.confirm_button.clicked.connect(self._submit)
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.confirm_button)
        layout.addLayout(actions)
        self.entry.returnPressed.connect(self._submit)
        self.entry.setFocus()

    def _submit(self) -> None:
        if self.entry.text().strip() != "DELETE ALL":
            self.error_label.setText(t("gui.clearFailed"))
            return
        self.error_label.clear()
        self.confirmed.emit()

    def set_pending(self, pending: bool) -> None:
        """清除期间锁定卡片，防止重复执行不可逆操作。"""
        self.entry.setEnabled(not pending)
        self.cancel_button.setEnabled(not pending)
        self.confirm_button.setEnabled(not pending)

    def show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.set_pending(False)

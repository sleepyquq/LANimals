"""LANimals Qt GUI 的轻量交互控件。"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
    Property,
    Signal,
)
from PySide6.QtGui import QColor, QMouseEvent, QPainter
from PySide6.QtWidgets import QAbstractButton, QComboBox, QLabel, QToolButton, QWidget

from lanimals.gui.qt_theme import QtTheme


class AnimatedToggle(QAbstractButton):
    """有原生绘制缓动的局域网访问开关。"""

    def __init__(self, theme: QtTheme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._knob_position = 0.0
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(38, 20)

        self._animation = QPropertyAnimation(self, b"knobPosition", self)
        self._animation.setDuration(160)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate_to_checked_state)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API 命名
        return QSize(38, 20)

    def _get_knob_position(self) -> float:
        return self._knob_position

    def _set_knob_position(self, value: float) -> None:
        self._knob_position = max(0.0, min(float(value), 1.0))
        self.update()

    knobPosition = Property(float, _get_knob_position, _set_knob_position)

    def _animate_to_checked_state(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._knob_position)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def set_state(self, checked: bool, *, animated: bool = False, emit: bool = False) -> None:
        """同步外部状态；刷新设置时不触发控制器回调。"""
        if self.isChecked() == checked:
            self._set_knob_position(1.0 if checked else 0.0)
            return

        previously_blocked = self.blockSignals(not emit)
        self.setChecked(checked)
        self.blockSignals(previously_blocked)
        if animated:
            self._animate_to_checked_state(checked)
        else:
            self._animation.stop()
            self._set_knob_position(1.0 if checked else 0.0)

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt API 命名
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track_color = self._theme.status_green if self.isChecked() else self._theme.entry_border
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(track_color))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 9, 9)

        knob_diameter = 16
        travel = self.width() - knob_diameter - 4
        x = 2 + travel * self._knob_position
        painter.setBrush(QColor("#ffffff" if not self._theme.is_dark else "#f6f1eb"))
        painter.drawEllipse(int(round(x)), 2, knob_diameter, knob_diameter)


class HoverToolButton(QToolButton):
    """统一窗口控制与返回按钮的轻量悬停反馈。"""

    def __init__(
        self,
        text: str,
        tooltip: str,
        theme: QtTheme,
        *,
        danger: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(26, 26)
        normal_text = theme.text_main if not danger else theme.text_muted
        hover_background = theme.danger if danger else theme.top_control_hover
        hover_text = "#ffffff" if danger else theme.text_main
        self.setStyleSheet(
            f"""
            QToolButton {{
                background: transparent;
                border: none;
                border-radius: 6px;
                color: {normal_text};
                font-size: 16px;
                font-family: 'Microsoft YaHei UI';
            }}
            QToolButton:hover {{
                background: {hover_background};
                color: {hover_text};
            }}
            QToolButton:pressed {{
                background: {hover_background};
            }}
            """
        )


class ClickableLabel(QLabel):
    """提供链接式点击语义的标签。"""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API 命名
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class WarmComboBox(QComboBox):
    """补绘一个稳定的下拉箭头，避免 Qt 样式表吞掉系统默认箭头。"""

    def __init__(self, theme: QtTheme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API 命名
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(self._theme.text_main))
        x = self.width() - 15
        y = self.height() // 2 - 2
        painter.drawLine(x - 4, y, x, y + 4)
        painter.drawLine(x, y + 4, x + 4, y)


class DragRegion(QWidget):
    """仅让顶栏空白区域负责拖动，按钮点击仍由按钮自身处理。"""

    def __init__(self, target_window: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._target_window = target_window
        self._drag_origin: QPoint | None = None
        # 顶栏仍可拖动，但保持普通箭头，避免误导为调整窗口大小。
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API 命名
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_origin = event.globalPosition().toPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API 命名
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            current = event.globalPosition().toPoint()
            self._target_window.move(self._target_window.pos() + current - self._drag_origin)
            self._drag_origin = current
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 - Qt API 命名
        self._drag_origin = None
        super().mouseReleaseEvent(event)


class PageHost(QWidget):
    """只动画页面内容，不触碰原生顶层窗口的尺寸、透明度或映射状态。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._pages: dict[str, QWidget] = {}
        self._current_name: str | None = None
        self._animation: QPropertyAnimation | None = None

    def add_page(self, name: str, page: QWidget) -> None:
        page.setParent(self)
        page.setGeometry(self.rect())
        page.hide()
        self._pages[name] = page

    def show_page(self, name: str, direction: int = 1) -> None:
        incoming = self._pages[name]
        if self._current_name == name:
            return

        if self._animation is not None:
            self._animation.stop()
            self._animation.deleteLater()
            self._animation = None

        outgoing = self._pages.get(self._current_name) if self._current_name else None
        if outgoing is None:
            incoming.setGeometry(self.rect())
            incoming.show()
            self._current_name = name
            return

        width = max(1, self.width())
        height = max(1, self.height())
        # 旧页面立即退出绘制树，避免在小窗口里产生内容残留或叠影。
        outgoing.hide()
        incoming.setGeometry(QRect(direction * 18, 0, width, height))
        incoming.show()
        incoming.raise_()
        self._current_name = name

        incoming_animation = QPropertyAnimation(incoming, b"pos", self)
        incoming_animation.setDuration(180)
        incoming_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        incoming_animation.setStartValue(incoming.pos())
        incoming_animation.setEndValue(QPoint(0, 0))

        def finish_transition() -> None:
            outgoing.move(0, 0)
            incoming.move(0, 0)
            self._animation = None

        incoming_animation.finished.connect(finish_transition)
        self._animation = incoming_animation
        incoming_animation.start()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API 命名
        super().resizeEvent(event)
        if self._animation is None:
            for page in self._pages.values():
                page.resize(event.size())

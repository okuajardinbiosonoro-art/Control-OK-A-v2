from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QTimer, Qt
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class ToastPalette:
    background: str
    border: str
    title: str
    message: str


_TOAST_PALETTES: dict[str, ToastPalette] = {
    "info": ToastPalette("#FFFDF9", "#DCCFB8", "#0B3B27", "#4F6259"),
    "success": ToastPalette("#EEF8F1", "#B7DFC5", "#0B3B27", "#3F5E51"),
    "warning": ToastPalette("#FFF5E6", "#E6C98F", "#432918", "#6A5139"),
    "error": ToastPalette("#FFF0EE", "#E1A59C", "#7B2C20", "#7B2C20"),
}


class ToastWidget(QFrame):
    def __init__(
        self,
        *,
        title: str,
        message: str,
        level: str = "info",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("toastNotification")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowFlags(Qt.WindowType.SubWindow | Qt.WindowType.FramelessWindowHint)

        palette = _TOAST_PALETTES.get(level, _TOAST_PALETTES["info"])
        self.setStyleSheet(
            (
                "QFrame#toastNotification {"
                f"background-color: {palette.background};"
                f"border: 1px solid {palette.border};"
                "border-radius: 14px;"
                "}"
                "QLabel { background: transparent; }"
                f"QLabel#toastTitle {{ color: {palette.title}; font-weight: 700; }}"
                f"QLabel#toastMessage {{ color: {palette.message}; }}"
            )
        )

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        accent = QFrame(self)
        accent.setFixedWidth(4)
        accent.setObjectName("toastAccent")
        accent.setStyleSheet(
            "QFrame#toastAccent {"
            f"background-color: {palette.border};"
            "border-radius: 2px;"
            "}"
        )
        root.addWidget(accent)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("toastTitle")
        self.message_label = QLabel(message, self)
        self.message_label.setObjectName("toastMessage")
        self.message_label.setWordWrap(True)

        text_col.addWidget(self.title_label)
        text_col.addWidget(self.message_label)
        root.addLayout(text_col, 1)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self._has_entered = False

        self._fade_animation = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_animation.setDuration(220)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._slide_animation = QPropertyAnimation(self, b"pos", self)
        self._slide_animation.setDuration(220)
        self._slide_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._dismiss_callback = None

    def animate_in(self, end_pos: QPoint) -> None:
        start_pos = QPoint(end_pos.x(), end_pos.y() + 18)
        self.move(start_pos)
        self._slide_animation.stop()
        self._slide_animation.setStartValue(start_pos)
        self._slide_animation.setEndValue(end_pos)
        self._slide_animation.start()
        self._fade_animation.stop()
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.start()
        self._has_entered = True

    def animate_out(self, end_pos: QPoint, on_finished) -> None:
        if self._dismiss_callback is not None:
            try:
                self._fade_animation.finished.disconnect(self._dismiss_callback)
            except (RuntimeError, TypeError):
                pass
        self._dismiss_callback = on_finished
        self._slide_animation.stop()
        self._slide_animation.setStartValue(self.pos())
        self._slide_animation.setEndValue(end_pos)
        self._slide_animation.start()
        self._fade_animation.stop()
        self._fade_animation.setStartValue(self._opacity.opacity())
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.finished.connect(self._dismiss_callback)
        self._fade_animation.start()


class ToastManager(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._toasts: list[ToastWidget] = []
        self.hide()

    def show_toast(
        self,
        *,
        title: str,
        message: str,
        level: str = "info",
        duration_ms: int = 3200,
    ) -> None:
        toast = ToastWidget(title=title, message=message, level=level, parent=self.parentWidget())
        toast.resize(360, toast.sizeHint().height())
        toast.show()
        self._toasts.append(toast)
        self.reposition_toasts()
        QTimer.singleShot(max(1200, int(duration_ms)), lambda: self._dismiss_toast(toast))

    def reposition_toasts(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        margin = 22
        gap = 10
        current_y = parent.height() - margin
        for toast in reversed(self._toasts):
            toast.adjustSize()
            width = min(max(toast.width(), 280), max(280, parent.width() - margin * 2))
            toast.resize(width, toast.sizeHint().height())
            current_y -= toast.height()
            target = QPoint(margin, current_y)
            if toast._has_entered:
                toast.move(target)
            else:
                toast.animate_in(target)
            current_y -= gap

    def _dismiss_toast(self, toast: ToastWidget) -> None:
        if toast not in self._toasts:
            return

        def _cleanup() -> None:
            try:
                toast.deleteLater()
            finally:
                if toast in self._toasts:
                    self._toasts.remove(toast)
                self.reposition_toasts()

        toast.animate_out(QPoint(toast.x(), toast.y() + 14), _cleanup)

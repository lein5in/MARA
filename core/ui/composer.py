from collections import deque

from PyQt5.QtCore import Qt, QSize, QRectF, pyqtSignal
from PyQt5.QtGui import QPainter, QColor
from PyQt5.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QPlainTextEdit, QSizePolicy, QStackedWidget, QVBoxLayout, QGraphicsOpacityEffect,
)

from core.ui import theme
from core.ui.theme import C
from core.ui.messages import hbox, label

PLACEHOLDER = "message mara"
PLACEHOLDER_VISION = "ask a follow-up about the screen"
PLACEHOLDER_LOCKED = "answer the confirmation above"


class InputBox(QPlainTextEdit):
    submitted = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("Input")
        self.setFont(theme.mono(13.5))
        self.setPlaceholderText(PLACEHOLDER)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setTabChangesFocus(True)
        self.document().setDocumentMargin(2)
        self.textChanged.connect(self._fit)
        self._fit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter) and not event.modifiers() & Qt.ShiftModifier:
            self.submitted.emit()
            return
        super().keyPressEvent(event)

    def _fit(self):
        lines = max(1, min(6, int(self.document().size().height())))
        line = self.fontMetrics().lineSpacing()
        self.setFixedHeight(max(28, lines * line + 10))


class Composer(QFrame):
    send = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("Composer")
        self.prompt = label("›", "ComposerPrompt", theme.mono(16, 600))
        self.input = InputBox()
        self.button = QPushButton("send  ↵")
        self.button.setObjectName("SendButton")
        self.button.setFont(theme.mono(12, 600))
        self.button.setFixedHeight(34)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.clicked.connect(self._send)
        self.input.submitted.connect(self._send)
        self.input.textChanged.connect(self._refresh)
        lay = hbox(self.prompt, self.input, self.button, spacing=12, margins=(16, 9, 9, 9))
        lay.setAlignment(self.prompt, Qt.AlignVCenter)
        self.setLayout(lay)
        self.locked = False
        self._placeholder = PLACEHOLDER
        self._refresh()

    def text(self) -> str:
        return self.input.toPlainText().strip()

    def _refresh(self):
        self.button.setEnabled(bool(self.text()) and not self.locked)

    def _send(self):
        text = self.text()
        if text and not self.locked:
            self.send.emit(text)

    def clear(self):
        self.input.clear()

    def set_vision_placeholder(self, on: bool):
        self._placeholder = PLACEHOLDER_VISION if on else PLACEHOLDER
        if not self.locked:
            self.input.setPlaceholderText(self._placeholder)

    def set_locked(self, locked: bool):
        self.locked = locked
        for w in (self, self.prompt):
            w.setProperty("locked", locked)
            w.style().unpolish(w)
            w.style().polish(w)
        self.input.setReadOnly(locked)
        self.input.setPlaceholderText(PLACEHOLDER_LOCKED if locked else self._placeholder)
        if locked:
            effect = QGraphicsOpacityEffect(self)
            effect.setOpacity(0.55)
            self.setGraphicsEffect(effect)
        else:
            self.setGraphicsEffect(None)
        self._refresh()


class LevelBars(QWidget):
    COUNT = 40

    def __init__(self):
        super().__init__()
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.levels: deque = deque([0.0] * self.COUNT, maxlen=self.COUNT)

    def push(self, level: float):
        self.levels.append(max(0.0, min(1.0, level)))
        self.update()

    def reset(self):
        self.levels = deque([0.0] * self.COUNT, maxlen=self.COUNT)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        gap = 3.0
        width = self.width()
        bar_w = min(4.0, (width - gap * (self.COUNT - 1)) / self.COUNT)
        total = bar_w * self.COUNT + gap * (self.COUNT - 1)
        step = bar_w + gap + (width - total) / max(1, self.COUNT - 1)
        color = QColor(C["accent"])
        for i, level in enumerate(self.levels):
            h = 4 + level * 32
            color.setAlphaF(1.0 if level > 0.02 else 0.35)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(i * step, (36 - h) / 2, bar_w, h), 1, 1)
        p.end()


class ListeningStrip(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("ListenStrip")
        self.setFixedHeight(62)
        mic_box = QFrame()
        mic_box.setObjectName("MicBox")
        mic_box.setFixedSize(36, 36)
        mic = QLabel()
        mic.setPixmap(theme.icon_pixmap("mic", C["on_accent"], 18, 2.0))
        mic_box.setLayout(hbox(mic, margins=(9, 9, 9, 9)))
        self.bars = LevelBars()
        self.rec = label("rec 00:00", "RecTime", theme.mono(13))
        self.rec.setAlignment(Qt.AlignRight)
        hint = label("release to send", "RecHint", theme.mono(11))
        hint.setAlignment(Qt.AlignRight)
        right = QVBoxLayout()
        right.setSpacing(5)
        right.addWidget(self.rec)
        right.addWidget(hint)
        lay = hbox(mic_box, self.bars, spacing=16, margins=(12, 0, 14, 0))
        lay.addLayout(right)
        self.setLayout(lay)

    def set_level(self, level: float, elapsed: float):
        self.bars.push(level)
        secs = int(elapsed)
        self.rec.setText(f"rec {secs // 60:02d}:{secs % 60:02d}")

    def reset(self):
        self.bars.reset()
        self.rec.setText("rec 00:00")


class Toggle(QPushButton):
    def __init__(self, text: str):
        super().__init__()
        self.setObjectName("Toggle")
        self.setCheckable(True)
        self.setFont(theme.mono(12))
        self.setFixedHeight(30)
        self.setCursor(Qt.PointingHandCursor)
        self._text = text
        self.toggled.connect(self._render)
        self._render(False)

    def _render(self, checked: bool):
        self.setText(f"[{'x' if checked else ' '}]  {self._text}")
        self.setAccessibleName(f"{self._text} {'on' if checked else 'off'}")

    def set_checked_silently(self, checked: bool):
        self.blockSignals(True)
        self.setChecked(checked)
        self._render(checked)
        self.blockSignals(False)


class Footer(QWidget):
    def __init__(self, key: str):
        super().__init__()
        self.silent = Toggle("silent")
        self.vision = Toggle("vision")
        self.lead = label("hold", "Hint", theme.mono(11.5))
        self.key = label(key.upper(), "KeyCap", theme.mono(11.5))
        self.key.setFixedHeight(20)
        self.key.setAlignment(Qt.AlignCenter)
        self.tail = label("to talk", "Hint", theme.mono(11.5))
        self.setLayout(hbox(self.silent, 8, self.vision, None, self.lead, 8, self.key, 8, self.tail))
        self.set_mode("idle")

    def set_mode(self, mode: str):
        self.key.setProperty("active", mode == "listening")
        self.key.style().unpolish(self.key)
        self.key.style().polish(self.key)
        if mode == "listening":
            self.lead.setText("holding")
            self.tail.hide()
        else:
            self.lead.setText("hold")
            self.tail.setText("to answer by voice" if mode == "confirm" else "to talk")
            self.tail.show()


class ComposerArea(QWidget):
    def __init__(self, key: str):
        super().__init__()
        self.composer = Composer()
        self.strip = ListeningStrip()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.composer)
        self.stack.addWidget(self.strip)
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.footer = Footer(key)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 12, 22, 18)
        lay.setSpacing(12)
        lay.addWidget(self.stack)
        lay.addWidget(self.footer)
        self._fit()
        self.composer.input.textChanged.connect(self._fit)

    def _fit(self):
        current = self.stack.currentWidget()
        self.stack.setFixedHeight(current.sizeHint().height() if current is self.composer else 62)

    def set_listening(self, on: bool):
        self.stack.setCurrentWidget(self.strip if on else self.composer)
        if on:
            self.strip.reset()
        self._fit()

    def sizeHint(self):
        return QSize(720, self.stack.height() + 30 + 42)

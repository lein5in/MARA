import math
import time

from PyQt5.QtCore import Qt, QTimer, QSettings, QPoint, pyqtSignal, QRect
from PyQt5.QtGui import QPainter, QColor
from PyQt5.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QScrollArea, QSizeGrip, QSystemTrayIcon, QMenu,
    QApplication, QGraphicsOpacityEffect,
)

from core import events as ev
from core.config import MODEL_LABEL, TRIGGER_KEY, WIN_W, WIN_H
from core.events import State
from core.ui import theme
from core.ui.theme import C
from core.ui.composer import ComposerArea
from core.ui.messages import DaySeparator, UserBlock, MaraBlock, hbox, label, stamp, dim

STATUS = {
    State.LISTENING: "listening",
    State.THINKING: "thinking",
    State.SPEAKING: "speaking",
    State.WAITING_CONFIRMATION: "waiting for confirmation",
    State.PAUSED: "paused",
}
ACTIVE = {State.LISTENING, State.THINKING, State.SPEAKING, State.WAITING_CONFIRMATION}


def pulse(t: float) -> float:
    return 0.7 + 0.3 * math.cos(2 * math.pi * t / 1.6)


class StatusDot(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(6, 6)
        self.color = C["accent"]
        self.opacity = 1.0

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(self.color)
        c.setAlphaF(self.opacity)
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(0, 0, 6, 6, 1, 1)
        p.end()


class Header(QFrame):
    new_conversation = pyqtSignal()
    expand = pyqtSignal()
    hide_window = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("Header")
        self.setFixedHeight(64)
        mono = QLabel("›_")
        mono.setObjectName("Monogram")
        mono.setFont(theme.mono(13, 600))
        mono.setFixedSize(32, 32)
        mono.setAlignment(Qt.AlignCenter)
        word = label("MARA", "Wordmark", theme.mono(15, 600, spacing_em=0.24))
        self.dot = StatusDot()
        self.status = label("", "StatusText", theme.mono(11.5))
        texts = QVBoxLayout()
        texts.setSpacing(5)
        texts.setContentsMargins(0, 0, 0, 0)
        texts.addStretch(1)
        texts.addWidget(word)
        status_row = hbox(self.dot, self.status, spacing=7)
        status_row.setAlignment(self.dot, Qt.AlignVCenter)
        texts.addLayout(status_row)
        texts.addStretch(1)
        self.buttons = {}
        btns = []
        for key, icon, tip, sig in (("new", "plus", "New conversation", self.new_conversation),
                                    ("expand", "expand", "Expand window", self.expand),
                                    ("hide", "minus", "Hide window", self.hide_window)):
            b = QPushButton()
            b.setObjectName("IconButton")
            b.setFixedSize(34, 34)
            b.setIcon(theme.icon(icon, C["tertiary"], 17))
            b.setToolTip(tip)
            b.setAccessibleName(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(sig)
            self.buttons[key] = b
            btns.append(b)
        lay = hbox(mono, 14, spacing=0, margins=(22, 0, 16, 0))
        lay.addLayout(texts)
        lay.addStretch(1)
        for b in btns:
            lay.addWidget(b)
            lay.addSpacing(2)
        self.setLayout(lay)

    def set_listening(self, on: bool):
        self.setProperty("listening", on)
        self.style().unpolish(self)
        self.style().polish(self)


class MainWindow(QWidget):
    send_text = pyqtSignal(str)
    confirm = pyqtSignal(str, bool)
    new_conversation = pyqtSignal()
    silent_toggled = pyqtSignal(bool)
    vision_toggled = pyqtSignal(bool)
    quit_requested = pyqtSignal()

    def __init__(self, settings: QSettings | None = None):
        super().__init__()
        self.setWindowTitle("MARA")
        self.setWindowIcon(theme.app_icon())
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(520, 480)
        self.settings = settings or QSettings("MARA", "MARA")
        self.state = State.IDLE
        self.vision = False
        self.silent = False
        self.block: MaraBlock | None = None
        self.live: UserBlock | None = None
        self.cards = {}
        self._drag: QPoint | None = None
        self._normal: QRect | None = None
        self._t0 = time.monotonic()
        self._build()
        self._timers()
        self._restore_geometry()
        self._tray()
        self.set_state(State.IDLE)

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.root = QFrame()
        self.root.setObjectName("Root")
        outer.addWidget(self.root)
        lay = QVBoxLayout(self.root)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)

        self.header = Header()
        self.header.new_conversation.connect(self._new_conversation)
        self.header.expand.connect(self.toggle_expand)
        self.header.hide_window.connect(self.hide)
        lay.addWidget(self.header)
        self.listen_bar = QFrame()
        self.listen_bar.setObjectName("ListenBar")
        self.listen_bar.setFixedHeight(2)
        self.listen_bar_fx = QGraphicsOpacityEffect(self.listen_bar)
        self.listen_bar.setGraphicsEffect(self.listen_bar_fx)
        self.listen_bar.hide()
        lay.addWidget(self.listen_bar)

        self.inner = QWidget()
        self.inner.setObjectName("ThreadInner")
        self.thread = QVBoxLayout(self.inner)
        self.thread.setContentsMargins(28, 26, 28, 12)
        self.thread.setSpacing(22)
        self.thread.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("Thread")
        self.scroll.setWidget(self.inner)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.verticalScrollBar().rangeChanged.connect(self._on_range)
        self._stick = True
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        lay.addWidget(self.scroll, 1)

        self.composer_area = ComposerArea(TRIGGER_KEY)
        self.composer = self.composer_area.composer
        self.footer = self.composer_area.footer
        self.composer.send.connect(self._send)
        self.footer.silent.toggled.connect(self.silent_toggled)
        self.footer.vision.toggled.connect(self.vision_toggled)
        lay.addWidget(self.composer_area)
        grip = QSizeGrip(self.root)
        grip.setFixedSize(14, 14)
        self.grip = grip

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.grip.move(self.root.width() - 16, self.root.height() - 16)

    def _timers(self):
        self.blink = QTimer(self)
        self.blink.timeout.connect(self._blink)
        self.blink.start(550)
        self._blink_on = True
        self.anim = QTimer(self)
        self.anim.timeout.connect(self._animate)
        self.anim.start(50)

    def _blink(self):
        self._blink_on = not self._blink_on
        if self.block and self.block.reply.streaming:
            self.block.set_cursor(self._blink_on)
        if self.live:
            self.live.set_cursor(self._blink_on)

    def _animate(self):
        a = pulse(time.monotonic() - self._t0) if self.state in ACTIVE else 1.0
        if abs(self.header.dot.opacity - a) > 0.01:
            self.header.dot.opacity = a
            self.header.dot.update()
        if self.listen_bar.isVisible():
            self.listen_bar_fx.setOpacity(a)

    def _tray(self):
        menu = QMenu()
        menu.addAction("Show MARA", self.show_raise)
        menu.addAction("New conversation", self._new_conversation)
        menu.addSeparator()
        menu.addAction("Quit MARA", self.quit_requested.emit)
        self.tray_menu = menu
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(theme.app_icon(), self)
        self.tray.setToolTip("MARA")
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.isVisible():
                self.hide()
            else:
                self.show_raise()

    def show_raise(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _restore_geometry(self):
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
            return
        self.resize(WIN_W, WIN_H)
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - WIN_W - 20, screen.bottom() - WIN_H - 20)

    def save_geometry(self):
        if self._normal is None:
            self.settings.setValue("geometry", self.saveGeometry())

    def hideEvent(self, event):
        self.save_geometry()
        super().hideEvent(event)

    def toggle_expand(self):
        if self._normal is None:
            self._normal = self.geometry()
            self.setGeometry(self.screen().availableGeometry())
        else:
            self.setGeometry(self._normal)
            self._normal = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.pos().y() <= self.header.height() + 1:
            self._drag = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.LeftButton and self._normal is None:
            self.move(event.globalPos() - self._drag)

    def mouseReleaseEvent(self, event):
        if self._drag is not None:
            self._drag = None
            self.save_geometry()

    def mouseDoubleClickEvent(self, event):
        if event.pos().y() <= self.header.height():
            self.toggle_expand()

    def _on_scroll(self, value):
        bar = self.scroll.verticalScrollBar()
        self._stick = value >= bar.maximum() - 24

    def _on_range(self, lo, hi):
        if self._stick:
            self.scroll.verticalScrollBar().setValue(hi)

    def _add(self, widget: QWidget, align=None):
        if self.thread.count() == 1:
            self.thread.addWidget(DaySeparator(f"today · {stamp()}"))
        if align is None:
            self.thread.addWidget(widget)
        else:
            self.thread.addWidget(widget, 0, align)
        self._stick = True

    def _send(self, text: str):
        self.send_text.emit(text)
        self.composer.clear()

    def _new_conversation(self):
        while self.thread.count() > 1:
            item = self.thread.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        self.block = None
        self.live = None
        self.cards = {}
        self.composer.set_locked(False)
        self.new_conversation.emit()

    def _ensure_block(self) -> MaraBlock:
        if self.block is None:
            self.block = MaraBlock()
            self.block.confirm_answered.connect(self.confirm)
            self._add(self.block, Qt.AlignLeft)
        return self.block

    def _status_text(self) -> str:
        if self.state in STATUS:
            return STATUS[self.state]
        return "ready · vision on" if self.vision else f"ready · {MODEL_LABEL}"

    def set_state(self, state: State):
        prev = self.state
        self.state = state
        listening = state == State.LISTENING
        self.header.status.setText(self._status_text())
        self.header.status.setProperty("active", state in ACTIVE)
        self.header.status.style().unpolish(self.header.status)
        self.header.status.style().polish(self.header.status)
        self.header.dot.color = {State.WAITING_CONFIRMATION: C["warn"], State.PAUSED: C["dim"]}.get(state, C["accent"])
        self.header.dot.update()
        self.header.set_listening(listening)
        self.listen_bar.setVisible(listening)
        self.composer_area.set_listening(listening)
        self.footer.set_mode("listening" if listening else "confirm" if state == State.WAITING_CONFIRMATION else "idle")
        if listening != (prev == State.LISTENING):
            self._dim_history(listening)

    def _dim_history(self, on: bool):
        widgets = [self.thread.itemAt(i).widget() for i in range(1, self.thread.count())]
        for w in widgets[-6:]:
            if w is not None and w is not self.live:
                dim(w, on)

    def set_modes(self, silent: bool, vision: bool):
        self.silent, self.vision = silent, vision
        self.footer.silent.set_checked_silently(silent)
        self.footer.vision.set_checked_silently(vision)
        self.composer.set_vision_placeholder(vision)
        self.header.status.setText(self._status_text())

    def on_event(self, event):
        if isinstance(event, ev.StateChanged):
            self.set_state(event.state)
        elif isinstance(event, ev.MicLevel):
            self.composer_area.strip.set_level(event.level, event.elapsed)
        elif isinstance(event, ev.UserTranscript):
            self._transcript(event)
        elif isinstance(event, ev.TurnStarted):
            self._turn_started(event)
        elif isinstance(event, ev.TextDelta):
            self._ensure_block().append_text(event.text)
        elif isinstance(event, ev.ToolStarted):
            block = self._ensure_block()
            block.finish()
            block.receipts.start(event.id, event.name, event.label)
        elif isinstance(event, ev.ToolFinished):
            self._ensure_block().receipts.finish(event.id, event.name, event.ok, event.duration, event.summary,
                                                 event.label)
        elif isinstance(event, ev.ConfirmationRequested):
            card = self._ensure_block().add_confirmation(event.id, event.title, event.description, event.tool,
                                                         " ".join(f"{k}={v}" for k, v in event.args.items()))
            self.cards[event.id] = card
            self.block.receipts.drop(event.id)
            self.composer.set_locked(True)
        elif isinstance(event, ev.ConfirmationResolved):
            card = self.cards.pop(event.id, None)
            if card:
                card.resolve(event.accepted)
            self.composer.set_locked(bool(self.cards))
        elif isinstance(event, (ev.Error, ev.Notice)):
            block = self._ensure_block()
            if isinstance(event, ev.Error):
                block.show_error(event.message)
            else:
                block.append_text(event.text)
                block.finish()
                self.block = None
        elif isinstance(event, ev.Done):
            self._done()
        elif isinstance(event, ev.ModeChanged):
            self.set_modes(event.silent, event.vision)
        elif isinstance(event, ev.ConversationReset):
            self.block = None
            self.thread.addWidget(DaySeparator(f"new conversation · {stamp()}"))
        elif isinstance(event, ev.ShowInterface):
            self.show_raise()
        elif isinstance(event, ev.HideInterface):
            self.hide()

    def _transcript(self, event: ev.UserTranscript):
        if event.final and not event.text.strip():
            if self.live:
                self.thread.removeWidget(self.live)
                self.live.deleteLater()
                self.live = None
            return
        if self.live is None:
            self.live = UserBlock("", "voice", live=True)
            self._add(self.live)
        self.live.set_text(event.text)

    def _turn_started(self, event: ev.TurnStarted):
        if self.block is not None:
            self._done()
        if event.source == "voice" and self.live is not None:
            self.live.set_live(False)
            self.live.set_text(event.text)
            self.live = None
        else:
            if self.live is not None:
                self.thread.removeWidget(self.live)
                self.live.deleteLater()
                self.live = None
            self._add(UserBlock(event.text, event.source))

    def _done(self):
        block, self.block = self.block, None
        if block is None:
            return
        block.finish()
        if block.is_empty():
            self.thread.removeWidget(block)
            block.deleteLater()

    def closeEvent(self, event):
        event.ignore()
        self.hide()

import re
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QScrollArea, QLabel,
    QFrame, QSizePolicy, QDesktopWidget
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor, QPainter, QBrush
from PyQt5.QtWebEngineWidgets import QWebEngineView

from core import events as ev
from core.config import WIN_W, WIN_H
from core.log import get_logger
log = get_logger(__name__)

BG_MAIN      = "#1c1c1e"
BG_MSG_MARA  = "#2b2b2e"
BG_MSG_YOU   = "#000000"
ACCENT       = "#f2f2f2"
ACCENT_DIM   = "#3a3a3d"
TEXT_PRIMARY = "#f2f2f2"
TEXT_SEC     = "#9a9a9a"
TEXT_DIM     = "#6b6b6e"
TEXT_YOU     = "#ffffff"
BORDER       = "#3a3a3d"
BORDER_LIGHT = "#454548"
PILL_BG      = "#2b2b2e"


def _font(size: int, bold: bool = False) -> QFont:
    return QFont("Segoe UI", size, QFont.Bold if bold else QFont.Normal)

WIN_STYLE = f"""
QWidget {{
    background: {BG_MAIN};
    color: {TEXT_PRIMARY};
    font-family: 'Segoe UI', sans-serif;
}}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent; width: 3px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_LIGHT}; border-radius: 1px; min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QLineEdit {{
    background: transparent; border: none;
    color: {TEXT_PRIMARY}; font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
}}
"""

INPUT_CONTAINER_STYLE = f"""
QWidget {{
    background: {PILL_BG};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 24px;
}}
"""

def _brand_avatar(size: int = 32, font_size: int = 14) -> QLabel:
    """Avatar plein — noir/gris foncé, lettre blanche. Utilisé dans le header fixe."""
    lbl = QLabel("M")
    lbl.setFixedSize(size, size)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setFont(_font(font_size, bold=True))
    lbl.setStyleSheet(f"""
        background: #000000;
        border: 1px solid {BORDER_LIGHT};
        border-radius: {size // 2}px;
        color: white;
    """)
    return lbl

def _outline_avatar(size: int = 22, font_size: int = 10) -> QLabel:
    """Avatar contour — cercle vide, sans remplissage. Utilisé sur les bulles MARA."""
    lbl = QLabel("M")
    lbl.setFixedSize(size, size)
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setFont(_font(font_size, bold=True))
    lbl.setStyleSheet(f"""
        background: transparent;
        border: 1px solid {TEXT_PRIMARY};
        border-radius: {size // 2}px;
        color: {TEXT_PRIMARY};
    """)
    return lbl

class StatusDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(8, 8)
        self._opacity = 1.0
        self._color = QColor("#505050")
        self._rising = False
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(1200)

    def set_color(self, hex_color: str):
        self._color = QColor(hex_color)
        self.update()

    def _tick(self):
        self._rising = not self._rising
        self._opacity = 1.0 if self._rising else 0.35
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(self._color)
        c.setAlphaF(self._opacity)
        p.setBrush(QBrush(c))
        p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, 8, 8)

class MARAVisualWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MARA — Visual")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(f"background: {BG_MAIN};")
        self._drag_pos = None
        self._build()
        screen = QDesktopWidget().screenGeometry()
        w, h = 860, 620
        self.setFixedSize(w, h)
        self.move(
            (screen.width() - w) // 2,
            (screen.height() - h) // 2
        )

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QWidget()
        bar.setFixedHeight(46)
        bar.setStyleSheet(f"background: {BG_MAIN}; border-bottom: 1px solid {BORDER};")
        blay = QHBoxLayout(bar)
        blay.setContentsMargins(20, 0, 14, 0)
        blay.setSpacing(10)

        title = QLabel("MARA")
        title.setFont(_font(12, bold=True))
        title.setStyleSheet(f"color: {TEXT_PRIMARY}; letter-spacing: 3px;")
        blay.addWidget(title)

        self._label = QLabel("Visual output")
        self._label.setFont(_font(11))
        self._label.setStyleSheet(f"color: {TEXT_DIM};")
        blay.addWidget(self._label)

        blay.addStretch()

        close_btn = QPushButton("×")
        close_btn.setFixedSize(28, 28)
        close_btn.setFont(_font(16))
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {TEXT_DIM}; border-radius: 4px;
            }}
            QPushButton:hover {{ color: {TEXT_SEC}; background: #222222; }}
        """)
        close_btn.clicked.connect(self.hide)
        blay.addWidget(close_btn)

        root.addWidget(bar)

        self._view = QWebEngineView()
        self._view.setStyleSheet("background: #1e1e1e;")
        root.addWidget(self._view, stretch=1)

    def show_html(self, html: str, label: str = "Visual output"):
        self._label.setText(label)
        self._view.setHtml(html)
        self.show()
        self.raise_()
        self.activateWindow()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos:
            self.move(event.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

def _format_display_text(text: str) -> str:
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```[a-zA-Z]*\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'^```\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[-*]\s+', '• ', text, flags=re.MULTILINE)
    return text.strip()

class MessageBubble(QWidget):
    def __init__(self, who: str, text: str = "", parent=None):
        super().__init__(parent)
        self.who = who
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._build(text)

    def _build(self, text: str):
        is_mara = self.who == "MARA"

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 6, 20, 6)
        outer.setSpacing(4)

        row = QHBoxLayout()
        row.setSpacing(10)

        if is_mara:
            row.addWidget(_outline_avatar(22, 10), alignment=Qt.AlignTop)
        else:
            row.addStretch()

        bubble = QWidget()
        bubble.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        bubble.setMaximumWidth(440)
        if is_mara:
            bubble.setStyleSheet(f"""
                background: {BG_MSG_MARA};
                border: 1px solid {BORDER};
                border-radius: 12px;
            """)
        else:
            bubble.setStyleSheet(f"""
                background: {BG_MSG_YOU};
                border-radius: 12px;
            """)

        blay = QVBoxLayout(bubble)
        blay.setContentsMargins(16, 12, 16, 12)
        blay.setSpacing(6)

        self._text_lbl = QLabel(_format_display_text(text))
        self._text_lbl.setWordWrap(True)
        self._text_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._text_lbl.setFont(_font(13))
        tcol = TEXT_PRIMARY if is_mara else TEXT_YOU
        self._text_lbl.setStyleSheet(f"color: {tcol}; background: transparent;")
        self._text_lbl.setTextFormat(Qt.PlainText)
        blay.addWidget(self._text_lbl)

        self._chips_row = QHBoxLayout()
        self._chips_row.setSpacing(6)
        self._chips_row.setContentsMargins(0, 2, 0, 0)
        blay.addLayout(self._chips_row)

        row.addWidget(bubble)
        if is_mara:
            row.addStretch()

        outer.addLayout(row)

        if not is_mara:
            meta = QHBoxLayout()
            meta.setContentsMargins(0, 0, 4, 0)
            meta.addStretch()
            ts = QLabel(datetime.now().strftime("%H:%M") + "  ✓")
            ts.setFont(_font(9))
            ts.setStyleSheet(f"color: {TEXT_DIM};")
            meta.addWidget(ts)
            outer.addLayout(meta)

    def append_text(self, chunk: str):
        self._text_lbl.setText(self._text_lbl.text() + chunk)

    def set_text(self, text: str):
        self._text_lbl.setText(_format_display_text(text))

    def add_chips(self, chips: list):
        while self._chips_row.count():
            item = self._chips_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for c in chips:
            if c:
                chip = QLabel(c)
                chip.setFont(_font(10))
                chip.setStyleSheet(f"""
                    color: {TEXT_DIM};
                    border: 1px solid {BORDER_LIGHT};
                    border-radius: 3px;
                    padding: 2px 8px;
                """)
                self._chips_row.addWidget(chip)
        self._chips_row.addStretch()

class MARAWindow(QWidget):
    def __init__(self, submit):
        super().__init__()
        self._submit = submit
        self._chips: list[str] = []
        self._mode = "TEXT"
        self._pending: MessageBubble | None = None
        self._msg_count = 0
        self._drag_pos = None
        self._is_fullscreen = False
        self._normal_geometry = None

        self._setup_window()
        self._build_ui()

        self._visual_win = MARAVisualWindow()

    def _setup_window(self):
        self.setWindowTitle("MARA")
        self.setMinimumWidth(WIN_W)
        self.setMinimumHeight(WIN_H)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(WIN_STYLE)
        screen = QDesktopWidget().screenGeometry()
        self.move(screen.width() - WIN_W - 20, screen.height() - WIN_H - 50)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_topbar())
        root.addWidget(self._sep())
        root.addWidget(self._build_log(), stretch=1)
        root.addWidget(self._sep())
        root.addWidget(self._build_input())

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(60)
        bar.setStyleSheet(f"background: {BG_MAIN};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 0, 16, 0)
        lay.setSpacing(12)

        lay.addWidget(_brand_avatar(32, 13))

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        text_col.setContentsMargins(0, 0, 0, 0)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title = QLabel("MARA")
        title.setFont(_font(14, bold=True))
        title.setStyleSheet(f"color: {TEXT_PRIMARY};")
        title_row.addWidget(title)

        self._dot = StatusDot()
        title_row.addWidget(self._dot, alignment=Qt.AlignVCenter)
        title_row.addStretch()
        text_col.addLayout(title_row)

        subtitle = QLabel("Local voice assistant")
        subtitle.setFont(_font(11))
        subtitle.setStyleSheet(f"color: {TEXT_SEC};")
        text_col.addWidget(subtitle)

        lay.addLayout(text_col)

        lay.addStretch()

        expand_btn = QPushButton("⤢")
        expand_btn.setFixedSize(30, 30)
        expand_btn.setFont(_font(13))
        expand_btn.setStyleSheet(self._icon_btn_style())
        expand_btn.clicked.connect(self.toggle_fullscreen)
        lay.addWidget(expand_btn)

        close_btn = QPushButton("−")
        close_btn.setFixedSize(30, 30)
        close_btn.setFont(_font(15))
        close_btn.setStyleSheet(self._icon_btn_style())
        close_btn.clicked.connect(self.hide)
        lay.addWidget(close_btn)

        return bar

    def _build_log(self) -> QScrollArea:
        self._log_inner = QWidget()
        self._log_inner.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._log_layout = QVBoxLayout(self._log_inner)
        self._log_layout.setContentsMargins(0, 12, 0, 0)
        self._log_layout.setSpacing(1)
        self._log_layout.addStretch()

        self._scroll = QScrollArea()
        self._scroll.setWidget(self._log_inner)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("background: transparent;")
        return self._scroll

    def _build_input(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setStyleSheet(f"background: {BG_MAIN};")
        wlay = QVBoxLayout(wrapper)
        wlay.setContentsMargins(20, 14, 20, 16)
        wlay.setSpacing(10)

        input_container = QWidget()
        input_container.setStyleSheet(INPUT_CONTAINER_STYLE)
        ilay = QHBoxLayout(input_container)
        ilay.setContentsMargins(18, 0, 8, 0)
        ilay.setSpacing(10)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Type your message...")
        self._input.setFont(_font(14))
        self._input.setFixedHeight(48)
        self._input.returnPressed.connect(self._send)
        ilay.addWidget(self._input)

        send_btn = QPushButton("↑")
        send_btn.setFixedSize(36, 36)
        send_btn.setFont(_font(15, bold=True))
        send_btn.setStyleSheet("""
            QPushButton {
                background: #000000;
                border: none; color: white;
                border-radius: 18px;
            }
            QPushButton:hover { background: #333333; }
            QPushButton:pressed { background: #000000; }
        """)
        send_btn.clicked.connect(self._send)
        ilay.addWidget(send_btn)

        wlay.addWidget(input_container)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(10)
        mode_row.setContentsMargins(4, 2, 4, 0)
        mode_row.addStretch()

        self._mode_btns: dict[str, QPushButton] = {}

        silent_btn = QPushButton("🔇  Silent mode")
        silent_btn.setFont(_font(10))
        silent_btn.setFixedHeight(26)
        silent_btn.setStyleSheet(self._mode_btn_style(False))
        silent_btn.clicked.connect(lambda: self._set_mode("SILENT"))
        self._mode_btns["SILENT"] = silent_btn
        mode_row.addWidget(silent_btn)

        mode_divider = QFrame()
        mode_divider.setFixedWidth(1)
        mode_divider.setFixedHeight(16)
        mode_divider.setStyleSheet(f"background: {BORDER_LIGHT};")
        mode_row.addWidget(mode_divider)

        vision_btn = QPushButton("👁  Vision mode")
        vision_btn.setFont(_font(10))
        vision_btn.setFixedHeight(26)
        vision_btn.setStyleSheet(self._mode_btn_style(False))
        vision_btn.clicked.connect(lambda: self._set_mode("VISION"))
        self._mode_btns["VISION"] = vision_btn
        mode_row.addWidget(vision_btn)

        mode_row.addStretch()
        wlay.addLayout(mode_row)

        return wrapper

    def _sep(self) -> QFrame:
        f = QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet(f"background: {BORDER};")
        return f

    def _icon_btn_style(self, active: bool = False) -> str:
        color = TEXT_PRIMARY if active else TEXT_SEC
        return f"""
            QPushButton {{
                background: transparent; border: none;
                color: {color}; border-radius: 4px; font-size: 15px;
            }}
            QPushButton:hover {{ color: {TEXT_PRIMARY}; background: {BG_MSG_MARA}; }}
        """

    def _mode_btn_style(self, active: bool) -> str:
        if active:
            return f"""
                QPushButton {{
                    background: {BG_MSG_MARA}; border: 1px solid {BORDER_LIGHT};
                    color: {TEXT_PRIMARY}; border-radius: 13px; padding: 4px 14px;
                    font-family: 'Segoe UI'; font-size: 10px; letter-spacing: 1px;
                }}
            """
        return f"""
            QPushButton {{
                background: transparent; border: 1px solid transparent;
                color: {TEXT_SEC}; border-radius: 13px; padding: 4px 14px;
                font-family: 'Segoe UI'; font-size: 10px; letter-spacing: 1px;
            }}
            QPushButton:hover {{ color: {TEXT_PRIMARY}; border-color: {BORDER_LIGHT}; }}
        """

    def _set_mode(self, mode: str):
        self._mode = "TEXT" if self._mode == mode else mode
        active_silent = self._mode == "SILENT"
        active_vision = self._mode == "VISION"

        self._mode_btns["SILENT"].setStyleSheet(self._mode_btn_style(active_silent))
        self._mode_btns["VISION"].setStyleSheet(self._mode_btn_style(active_vision))

    def _send(self):
        text = self._input.text().strip()
        if not text:
            return
        if self._submit(text, "typed"):
            self._input.clear()

    def _add_bubble(self, bubble: MessageBubble):
        idx = self._log_layout.count() - 1
        self._log_layout.insertWidget(idx, bubble)
        self._msg_count += 1
        self._scroll_bottom()

    def _scroll_bottom(self):
        QTimer.singleShot(60, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    def on_status(self, status: str):
        colors = {
            "THINKING":    "#c5c5c5",
            "SPEAKING":    "#f2f2f2",
            "LISTENING":   "#9a9a9a",
            "PAUSED":      "#5a5a5a",
            "IDLE":        "#3a3a3d",
        }
        self._dot.set_color(colors.get(status, "#505050"))

    def on_mara_stream_start(self):
        if self._pending:
            return
        bubble = MessageBubble("MARA")
        self._add_bubble(bubble)
        self._pending = bubble

    def on_mara_chunk(self, chunk: str):
        if self._pending:
            self._pending.append_text(chunk)
            self._scroll_bottom()

    def on_mara_done(self, vocal: str, chips: list):
        if self._pending:
            if vocal:
                self._pending.set_text(vocal)
            if chips:
                self._pending.add_chips(chips)
            self._pending = None
        elif vocal:
            bubble = MessageBubble("MARA", vocal)
            self._add_bubble(bubble)
        self._scroll_bottom()

    def on_user_message(self, text: str):
        bubble = MessageBubble("YOU", text)
        self._add_bubble(bubble)

    def on_event(self, event):
        if isinstance(event, ev.TurnStarted):
            self.on_user_message(event.text)
            self._chips = []
        elif isinstance(event, ev.TextDelta):
            self.on_mara_stream_start()
            self.on_mara_chunk(event.text)
        elif isinstance(event, ev.ToolFinished):
            self._chips.append(event.name if event.ok else f"{event.name} failed")
        elif isinstance(event, ev.ConfirmationRequested):
            self.on_mara_done(f"{event.title}: {event.description} Say yes or cancel.", [event.tool])
        elif isinstance(event, ev.Error):
            self.on_mara_done(event.message, [])
        elif isinstance(event, ev.Done):
            if self._pending or self._chips:
                self.on_mara_done("", self._chips)
            self._chips = []
        elif isinstance(event, ev.Visual):
            self.on_visual(event.html, event.title)
        elif isinstance(event, ev.StateChanged):
            self.on_status(event.state.value.upper())
        elif isinstance(event, ev.ShowInterface):
            self.show()
        elif isinstance(event, ev.HideInterface):
            self.hide()

    def on_visual(self, html: str, label: str):
        self._visual_win.show_html(html, label)

    def toggle_fullscreen(self):
        if not self._is_fullscreen:
            self._normal_geometry = self.geometry()
            self.setWindowFlags(Qt.FramelessWindowHint)
            self.setGeometry(QDesktopWidget().screenGeometry())
            self._is_fullscreen = True
        else:
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            if self._normal_geometry:
                self.setGeometry(self._normal_geometry)
            self._is_fullscreen = False
        self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self._is_fullscreen:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos and not self._is_fullscreen:
            self.move(event.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

class MARAWorker(QThread):
    sig_event = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        from core.listener import listen
        from core.session import Session
        self.session = Session(self.sig_event.emit, listen_fn=listen)

    def submit(self, text: str, source: str = "typed") -> bool:
        return self.session.submit(text, source)

    def run(self):
        self.session.run()

    def stop(self):
        self.session.stop()

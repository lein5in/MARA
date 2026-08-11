import sys
import re
import json
import queue
import threading
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QScrollArea, QLabel,
    QFrame, QSizePolicy, QDesktopWidget
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QColor, QPainter, QBrush
from PyQt5.QtWebEngineWidgets import QWebEngineView

from core.brain import _build_system_prompt

READ_ACTIONS = {"browser_read", "get_volume", "get_brightness", "wifi_status", "get_time"}

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

WIN_W = 680
WIN_H = 700

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
    def __init__(self, text_queue: queue.Queue):
        super().__init__()
        self._text_queue = text_queue
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
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background: #000000;
                border: none; color: white;
                border-radius: 18px;
            }}
            QPushButton:hover {{ background: #333333; }}
            QPushButton:pressed {{ background: #000000; }}
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
        is_pwd = (self._input.echoMode() == QLineEdit.Password)
        if self._mode == "VISION":
            self._text_queue.put(f"__VISION__{text}")
        else:
            self._text_queue.put(text)
        if not is_pwd:
            self.on_user_message(text)
        self._input.clear()
        if is_pwd:
            self.on_password_mode(False)

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
            "OPERATIONAL": "#6b6b6b",
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

    def on_password_mode(self, active: bool):
        if active:
            self._input.setEchoMode(QLineEdit.Password)
            self._input.setPlaceholderText("Enter password (hidden)...")
            self._input.setFocus()
        else:
            self._input.setEchoMode(QLineEdit.Normal)
            self._input.setPlaceholderText("Message MARA...")

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
    sig_status        = pyqtSignal(str)
    sig_stream_start  = pyqtSignal()
    sig_chunk         = pyqtSignal(str)
    sig_done          = pyqtSignal(str, list)
    sig_user_msg      = pyqtSignal(str)
    sig_password_mode = pyqtSignal(bool)
    sig_show          = pyqtSignal()
    sig_hide          = pyqtSignal()
    sig_visual        = pyqtSignal(str, str)

    _PWD_KW  = {"password", "mot de passe", "كلمة المرور", "pass"}
    _OFFLINE = {
        "fr": "Système en pause. Maintiens ENTRÉE et dis mon nom pour me réveiller.",
        "en": "System offline. Hold Enter and say my name to wake me.",
        "ar": "النظام في وضع الإيقاف. اضغط Enter وقل اسمي لإيقاظي.",
    }
    _WAKE = {"mara"}

    _VISUAL_SYSTEM = """You are MARA's visual renderer. Generate a single self-contained HTML page that visually represents the requested data or concept.

Rules:
- Return ONLY raw HTML. No markdown, no code fences, no explanation.
- Use inline CSS only. No external dependencies except Chart.js if needed for charts:
  <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
- Dark theme: background #1e1e1e, text #e8e8e8, accents in subtle greys or soft blues.
- Clean, minimal, professional design. Generous whitespace.
- For charts: use Chart.js with dark styling.
- For tables: clean borders, alternating row colors.
- For diagrams/schemas: use SVG inline.
- For summaries: structured layout with clear hierarchy.
- The page must be fully rendered with no interactivity unless explicitly requested.
- Start your response directly with <!DOCTYPE html>"""

    def __init__(self, text_queue: queue.Queue):
        super().__init__()
        self._q = text_queue
        self._running = True
        self._voice_q = queue.Queue()

    def _voice_loop(self, listen_fn):
        while self._running:
            text = listen_fn()
            if text:
                self._voice_q.put(text)

    def _get_input(self) -> tuple[str, str]:
        while self._running:
            try:
                text = self._q.get_nowait()
                return text, "ui"
            except queue.Empty:
                pass
            try:
                text = self._voice_q.get(timeout=0.05)
                return text, "voice"
            except queue.Empty:
                pass
        return "", "voice"

    def _pause_loop(self, memory, system, speak_fn):
        self.sig_status.emit("PAUSED")
        while system.is_paused(memory) and self._running:
            try:
                text = self._q.get_nowait()
                if any(w in text.lower() for w in self._WAKE):
                    system.cancel_pause(memory)
                    self.sig_status.emit("OPERATIONAL")
                    speak_fn("I'm back.")
                    return
            except queue.Empty:
                pass
            try:
                text = self._voice_q.get(timeout=0.1)
                if any(w in text.lower() for w in self._WAKE):
                    system.cancel_pause(memory)
                    self.sig_status.emit("OPERATIONAL")
                    speak_fn("I'm back.")
                    return
                else:
                    lang = system._current_lang
                    msg = self._OFFLINE.get(lang, self._OFFLINE["en"])
                    speak_fn(msg)
            except queue.Empty:
                pass

    def _handle_work_mode(self, language, speak_stream_fn, execute_fn,
                          get_work_mode_ask, get_work_mode_launch):
        ask_msg = get_work_mode_ask(language)
        self.sig_done.emit(ask_msg, [])
        print(f"MARA : {ask_msg}")
        speak_stream_fn(iter([ask_msg]))

        user_input, source = self._get_input()
        if source == "voice" and user_input:
            self.sig_user_msg.emit(user_input)

        skip = {"nothing", "none", "no", "rien", "non", "لا", "skip"}
        is_skip = not user_input or any(w in user_input.lower() for w in skip)

        actions = []
        if not is_skip and user_input.strip():
            clean = user_input.strip().rstrip(".,!?")
            actions.append({"type": "open_with", "name": clean, "app": "code",
                            "folder": "%USERPROFILE%", "is_folder": True})
        else:
            actions.append({"type": "run", "command": "code"})

        actions.append({"type": "run", "command": "chrome"})
        actions.append({"type": "run", "command": "msedge"})

        has_file = not is_skip
        launch_msg = get_work_mode_launch(language, has_file)
        chips = [a.get("command", a.get("name", a.get("type", ""))) for a in actions]
        self.sig_done.emit(launch_msg, chips)
        print(f"MARA : {launch_msg}")
        speak_stream_fn(iter([launch_msg]))
        execute_fn(actions)

    def _handle_visual(self, prompt: str, speak_stream_fn):
        from anthropic import Anthropic
        import os
        from dotenv import load_dotenv
        load_dotenv()

        self.sig_status.emit("THINKING")

        thinking_msg = "Generating your visual, one moment."
        self.sig_done.emit(thinking_msg, [])
        speak_stream_fn(iter([thinking_msg]))

        try:
            client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=self._VISUAL_SYSTEM,
                messages=[{"role": "user", "content": prompt}]
            )
            html = response.content[0].text.strip()

            if html.startswith("```"):
                html = re.sub(r'^```[a-z]*\n?', '', html)
                html = re.sub(r'\n?```$', '', html)
                html = html.strip()

            label = prompt[:48] + ("..." if len(prompt) > 48 else "")

            self.sig_visual.emit(html, label)

            done_msg = "Here it is."
            self.sig_done.emit(done_msg, [])
            speak_stream_fn(iter([done_msg]))

        except Exception as e:
            err = f"Visual generation error: {e}"
            print(f"[Visual] {err}")
            self.sig_done.emit(err, [])

        self.sig_status.emit("OPERATIONAL")

    def run(self):
        from core.brain import ask_mara_stream, get_work_mode_ask, get_work_mode_launch
        from core.listener import listen
        from core.voice import speak, speak_stream_sentences
        from core.executor import execute, needs_confirmation
        from core import system
        from memory.memory import Memory

        memory = Memory()

        voice_thread = threading.Thread(
            target=self._voice_loop, args=(listen,), daemon=True
        )
        voice_thread.start()

        while self._running:

            if system.is_paused(memory):
                self._pause_loop(memory, system, speak)
                continue

            user_input, source = self._get_input()

            if system.is_paused(memory):
                continue
            if not user_input:
                continue

            if user_input.startswith("__CMD__"):
                cmd = user_input.replace("__CMD__", "")
                if cmd == "silent_toggle":
                    user_input = "toggle silent mode"
                else:
                    continue

            if user_input.startswith("__VISION__"):
                prompt = user_input.replace("__VISION__", "").strip()
                self._handle_vision(prompt, system, memory, speak_stream_sentences,
                                   speak, execute, needs_confirmation, ask_mara_stream)
                continue

            if "quit" in user_input.lower():
                speak("À bientôt.")
                self._running = False
                break

            if source == "voice":
                self.sig_user_msg.emit(user_input)

            self.sig_status.emit("THINKING")
            stream = ask_mara_stream(user_input)
            first = next(stream, "")

            if first.startswith("__WORK_MODE__"):
                language = first.replace("__WORK_MODE__", "").strip() or "en"
                self._handle_work_mode(language, speak_stream_sentences, execute,
                                       get_work_mode_ask, get_work_mode_launch)
                self.sig_status.emit("OPERATIONAL")
                continue

            if first.startswith("__UI_SHOW__"):
                language = first.replace("__UI_SHOW__", "").strip() or "en"
                from core.brain import MEMORY_RESPONSES
                msg = MEMORY_RESPONSES["ui_show"].get(language, "Here I am.")
                self.sig_show.emit()
                self.sig_done.emit(msg, [])
                print(f"MARA : {msg}")
                speak_stream_sentences(iter([msg]))
                self.sig_status.emit("OPERATIONAL")
                continue

            if first.startswith("__UI_HIDE__"):
                language = first.replace("__UI_HIDE__", "").strip() or "en"
                from core.brain import MEMORY_RESPONSES
                msg = MEMORY_RESPONSES["ui_hide"].get(language, "Going dark.")
                self.sig_done.emit(msg, [])
                print(f"MARA : {msg}")
                speak_stream_sentences(iter([msg]))
                self.sig_hide.emit()
                self.sig_status.emit("OPERATIONAL")
                continue

            if first.startswith("__VISION__"):
                prompt = first.replace("__VISION__", "").strip()
                self._handle_vision(prompt, system, memory, speak_stream_sentences,
                                   speak, execute, needs_confirmation, ask_mara_stream)
                self.sig_status.emit("IDLE")
                continue

            if first.startswith("__VISION_CODE__"):
                prompt = first.replace("__VISION_CODE__", "").strip()
                self._handle_vision_code(prompt, speak_stream_sentences)
                self.sig_status.emit("IDLE")
                continue

            if first.startswith("__VISUAL__"):
                prompt = first.replace("__VISUAL__", "").strip()
                self._handle_visual(prompt, speak_stream_sentences)
                continue

            self.sig_stream_start.emit()
            self._consume_stream(stream, first, system, memory, speak_stream_sentences,
                                 speak, execute, needs_confirmation, ask_mara_stream)

    def _consume_stream(self, stream, first, system, memory, speak_stream_sentences,
                        speak, execute, needs_confirmation, ask_mara_stream):
        full_response = first
        self.sig_chunk.emit(first)

        for chunk in stream:
            if not self._running:
                break
            full_response += chunk
            self.sig_chunk.emit(chunk)

        if system.is_paused(memory):
            self.sig_done.emit("", [])
            return

        actions = []
        vocal = full_response

        try:
            m = re.search(r'\{.*"actions"\s*:.*\}', full_response, re.DOTALL)
            if m:
                parsed = json.loads(m.group())
                if isinstance(parsed, dict) and "actions" in parsed:
                    vocal = parsed.get("response", "")
                    actions = parsed.get("actions", [])
        except (json.JSONDecodeError, AttributeError):
            pass

        chips = []
        for a in actions:
            label = a.get("command") or a.get("site") or a.get("type", "")
            if label:
                chips.append(label)

        if any(kw in vocal.lower() for kw in self._PWD_KW):
            self.sig_password_mode.emit(True)

        self.sig_done.emit(vocal, chips)
        print(f"MARA : {vocal or full_response}")

        if vocal:
            self.sig_status.emit("SPEAKING")
            if actions:
                speak_stream_sentences(iter([vocal]))
            else:
                speak_stream_sentences(iter([full_response]))

        self.sig_status.emit("OPERATIONAL")

        if not actions:
            return

        if needs_confirmation(actions):
            confirm = "Cette action nécessite ta confirmation. Tu confirmes ?"
            self.sig_done.emit(confirm, [])
            print(f"MARA : {confirm}")
            speak(confirm)
            reply, _ = self._get_input()
            if not any(w in (reply or "").lower() for w in ["yes","oui","confirm","go","ok"]):
                cancel = "Action annulée."
                self.sig_done.emit(cancel, [])
                print(f"MARA : {cancel}")
                speak(cancel)
                return

        results = execute(actions)

        for action, result in zip(actions, results):
            atype = action.get("type")

            if atype == "browser_read" and result and not result.startswith("Erreur"):
                self.sig_status.emit("THINKING")
                self.sig_stream_start.emit()
                summary_prompt = (f"Here is the content read from the browser. "
                                  f"Summarize it naturally and briefly: {result}")
                sr = ""
                for chunk in ask_mara_stream(summary_prompt):
                    sr += chunk
                    self.sig_chunk.emit(chunk)
                self.sig_done.emit(sr, [])
                print(f"MARA (lecture) : {sr}")
                self.sig_status.emit("SPEAKING")
                speak_stream_sentences(iter([sr]))
                self.sig_status.emit("OPERATIONAL")

            elif atype in READ_ACTIONS and result and not result.startswith("Erreur"):
                self.sig_done.emit(result, [])
                print(f"MARA ({atype}) : {result}")
                self.sig_status.emit("SPEAKING")
                speak_stream_sentences(iter([result]))
                self.sig_status.emit("OPERATIONAL")

            elif atype == "pause" and result:
                self.sig_done.emit(result, [])
                print(f"MARA (pause) : {result}")
                speak_stream_sentences(iter([result]))

            elif atype in ("silent_on", "silent_off") and result:
                self.sig_done.emit(result, [])
                print(f"MARA ({atype}) : {result}")
                speak_stream_sentences(iter([result]))

    def _handle_vision(self, prompt, system, memory, speak_stream_sentences,
                       speak, execute, needs_confirmation, ask_mara_stream):
        from core import system as sys_mod
        import base64

        result = sys_mod.take_screenshot_for_vision()
        if not result:
            msg = "I can not take a screenshot right now."
            self.sig_done.emit(msg, [])
            print(f"MARA : {msg}")
            return

        self.sig_status.emit("THINKING")

        with open(result, "rb") as f:
            img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

        from core.brain import ask_mara_vision_stream
        stream = ask_mara_vision_stream(prompt, img_b64)
        first = next(stream, "")

        self.sig_stream_start.emit()
        self._consume_stream(stream, first, system, memory, speak_stream_sentences,
                             speak, execute, needs_confirmation, ask_mara_stream)
        self.sig_status.emit("IDLE")

    def _handle_vision_code(self, prompt, speak_stream_sentences):
        from core import system as sys_mod
        import base64

        result = sys_mod.take_screenshot_for_vision()
        if not result:
            msg = "I can not take a screenshot right now."
            self.sig_done.emit(msg, [])
            print(f"MARA : {msg}")
            return

        self.sig_status.emit("THINKING")
        thinking_msg = "Let me look at your code."
        self.sig_done.emit(thinking_msg, [])
        print(f"MARA : {thinking_msg}")
        speak_stream_sentences(iter([thinking_msg]))

        with open(result, "rb") as f:
            img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

        from core.brain import ask_mara_vision_code
        summary, html = ask_mara_vision_code(prompt, img_b64)

        self.sig_stream_start.emit()
        self.sig_chunk.emit(summary)
        self.sig_done.emit(summary, [])
        print(f"MARA (vision code) : {summary}")

        self.sig_status.emit("SPEAKING")
        speak_stream_sentences(iter([summary]))

        if html:
            label = (prompt or "Code review")[:48]
            self.sig_visual.emit(html, label)

        self.sig_status.emit("IDLE")

    def stop(self):
        self._running = False
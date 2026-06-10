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

# ─── Palette ──────────────────────────────────────────────────────────────────
BG_MAIN      = "#1a1a1a"
BG_MSG_MARA  = "#1f1f1f"
BG_MSG_YOU   = "#191919"
ACCENT       = "#c8c8c8"
ACCENT_DIM   = "#606060"
TEXT_PRIMARY = "#e8e8e8"
TEXT_SEC     = "#888888"
TEXT_DIM     = "#3a3a3a"
TEXT_YOU     = "#aaaaaa"
BORDER       = "#252525"
BORDER_LIGHT = "#2e2e2e"

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
    background: #333333; border-radius: 1px; min-height: 30px;
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
    background: #202020;
    border: 1px solid {BORDER_LIGHT};
    border-radius: 10px;
}}
"""


# ══════════════════════════════════════════════════════════════════════════════
# STATUS DOT
# ══════════════════════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════════════════════
# VISUAL WINDOW — rendu HTML pour graphes, schémas, tableaux
# ══════════════════════════════════════════════════════════════════════════════

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

        # Topbar
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

        # WebEngine view
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


# ══════════════════════════════════════════════════════════════════════════════
# MESSAGE BUBBLE
# ══════════════════════════════════════════════════════════════════════════════

class MessageBubble(QWidget):
    def __init__(self, who: str, text: str = "", parent=None):
        super().__init__(parent)
        self.who = who
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._build(text)

    def _build(self, text: str):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        container = QWidget()
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        bg = BG_MSG_MARA if self.who == "MARA" else BG_MSG_YOU
        container.setStyleSheet(f"background: {bg};")

        inner = QVBoxLayout(container)
        inner.setContentsMargins(28, 18, 28, 18)
        inner.setSpacing(8)

        # Header
        hrow = QHBoxLayout()
        hrow.setSpacing(12)

        who_lbl = QLabel(self.who)
        who_lbl.setFont(_font(13, bold=True))
        col = ACCENT if self.who == "MARA" else TEXT_SEC
        who_lbl.setStyleSheet(f"color: {col}; letter-spacing: 1px;")
        hrow.addWidget(who_lbl)

        ts = QLabel(datetime.now().strftime("%H:%M"))
        ts.setFont(_font(11))
        ts.setStyleSheet(f"color: {TEXT_DIM};")
        hrow.addWidget(ts)
        hrow.addStretch()
        inner.addLayout(hrow)

        # Text
        self._text_lbl = QLabel(text)
        self._text_lbl.setWordWrap(True)
        self._text_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._text_lbl.setFont(_font(14))
        tcol = TEXT_PRIMARY if self.who == "MARA" else TEXT_YOU
        self._text_lbl.setStyleSheet(f"color: {tcol};")
        self._text_lbl.setTextFormat(Qt.PlainText)
        inner.addWidget(self._text_lbl)

        # Chips
        self._chips_row = QHBoxLayout()
        self._chips_row.setSpacing(6)
        self._chips_row.setContentsMargins(0, 2, 0, 0)
        inner.addLayout(self._chips_row)

        outer.addWidget(container)

    def append_text(self, chunk: str):
        self._text_lbl.setText(self._text_lbl.text() + chunk)

    def set_text(self, text: str):
        self._text_lbl.setText(text)

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


# ══════════════════════════════════════════════════════════════════════════════
# FENÊTRE PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════════

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

        # Fenêtre visuelle — créée une fois, réutilisée
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
        bar.setFixedHeight(54)
        bar.setStyleSheet(f"background: {BG_MAIN};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(24, 0, 16, 0)
        lay.setSpacing(10)

        self._dot = StatusDot()
        lay.addWidget(self._dot)

        name = QLabel("MARA")
        name.setFont(_font(14, bold=True))
        name.setStyleSheet(f"color: {TEXT_PRIMARY}; letter-spacing: 3px;")
        lay.addWidget(name)

        self._status_lbl = QLabel("OPERATIONAL")
        self._status_lbl.setFont(_font(10))
        self._status_lbl.setStyleSheet(f"color: {TEXT_DIM}; letter-spacing: 1px;")
        lay.addWidget(self._status_lbl)

        lay.addStretch()

        for symbol, slot in [("⤢", self.toggle_fullscreen), ("−", self.hide)]:
            btn = QPushButton(symbol)
            btn.setFixedSize(30, 30)
            btn.setFont(_font(13))
            btn.setStyleSheet(self._icon_btn_style())
            btn.clicked.connect(slot)
            lay.addWidget(btn)

        return bar

    def _build_log(self) -> QScrollArea:
        self._log_inner = QWidget()
        self._log_inner.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._log_layout = QVBoxLayout(self._log_inner)
        self._log_layout.setContentsMargins(0, 0, 0, 0)
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
        ilay.setContentsMargins(16, 0, 10, 0)
        ilay.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Message MARA...")
        self._input.setFont(_font(14))
        self._input.setFixedHeight(48)
        self._input.returnPressed.connect(self._send)
        ilay.addWidget(self._input)

        send_btn = QPushButton("↑")
        send_btn.setFixedSize(34, 34)
        send_btn.setFont(_font(15, bold=True))
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_DIM}; border: none; color: {BG_MAIN};
                border-radius: 7px;
            }}
            QPushButton:hover {{ background: {ACCENT}; }}
            QPushButton:pressed {{ background: #909090; }}
        """)
        send_btn.clicked.connect(self._send)
        ilay.addWidget(send_btn)

        wlay.addWidget(input_container)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        mode_row.setContentsMargins(4, 0, 4, 0)

        self._mode_btns: dict[str, QPushButton] = {}
        for m in ["SILENT", "VISION"]:
            btn = QPushButton(m)
            btn.setFont(_font(10))
            btn.setFixedHeight(28)
            btn.setStyleSheet(self._mode_btn_style(False))
            btn.clicked.connect(lambda _, mode=m: self._set_mode(mode))
            self._mode_btns[m] = btn
            mode_row.addWidget(btn)

        mode_row.addStretch()
        wlay.addLayout(mode_row)

        return wrapper

    def _sep(self) -> QFrame:
        f = QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet(f"background: {BORDER};")
        return f

    def _icon_btn_style(self) -> str:
        return f"""
            QPushButton {{
                background: transparent; border: none;
                color: {TEXT_DIM}; border-radius: 4px; font-size: 15px;
            }}
            QPushButton:hover {{ color: {TEXT_SEC}; background: #222222; }}
        """

    def _mode_btn_style(self, active: bool) -> str:
        if active:
            return f"""
                QPushButton {{
                    background: #272727; border: 1px solid {BORDER_LIGHT};
                    color: {ACCENT}; border-radius: 5px; padding: 4px 14px;
                    font-family: 'Segoe UI'; font-size: 10px; letter-spacing: 1px;
                }}
            """
        return f"""
            QPushButton {{
                background: transparent; border: 1px solid transparent;
                color: #555555; border-radius: 5px; padding: 4px 14px;
                font-family: 'Segoe UI'; font-size: 10px; letter-spacing: 1px;
            }}
            QPushButton:hover {{ color: {TEXT_SEC}; border-color: {BORDER}; }}
        """

    def _set_mode(self, mode: str):
        self._mode = "TEXT" if self._mode == mode else mode
        for m, btn in self._mode_btns.items():
            btn.setStyleSheet(self._mode_btn_style(m == self._mode))

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

    # ── Slots publics ─────────────────────────────────────────────────────────

    def on_status(self, status: str):
        self._status_lbl.setText(status)
        colors = {
            "THINKING":    "#8888ff",
            "SPEAKING":    "#88cc88",
            "LISTENING":   "#ccaa44",
            "PAUSED":      "#666666",
            "OPERATIONAL": "#505050",
            "IDLE":        "#383838",
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

    # ── Window controls ───────────────────────────────────────────────────────

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


# ══════════════════════════════════════════════════════════════════════════════
# WORKER THREAD
# ══════════════════════════════════════════════════════════════════════════════

class MARAWorker(QThread):
    sig_status        = pyqtSignal(str)
    sig_stream_start  = pyqtSignal()
    sig_chunk         = pyqtSignal(str)
    sig_done          = pyqtSignal(str, list)
    sig_user_msg      = pyqtSignal(str)
    sig_password_mode = pyqtSignal(bool)
    sig_show          = pyqtSignal()
    sig_hide          = pyqtSignal()
    sig_visual        = pyqtSignal(str, str)   # html, label

    _PWD_KW  = {"password", "mot de passe", "كلمة المرور", "pass"}
    _OFFLINE = {
        "fr": "Système en pause. Maintiens ENTRÉE et dis mon nom pour me réveiller.",
        "en": "System offline. Hold Enter and say my name to wake me.",
        "ar": "النظام في وضع الإيقاف. اضغط Enter وقل اسمي لإيقاظي.",
    }
    _WAKE = {"mara"}

    # Prompt système pour la génération de visuels
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
        """Génère un visuel HTML via Claude et l'affiche dans MARAVisualWindow."""
        from anthropic import Anthropic
        import os
        from dotenv import load_dotenv
        load_dotenv()

        self.sig_status.emit("THINKING")

        # Message vocal pendant la génération
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

            # Nettoyage au cas où Claude aurait quand même mis des fences
            if html.startswith("```"):
                html = re.sub(r'^```[a-z]*\n?', '', html)
                html = re.sub(r'\n?```$', '', html)
                html = html.strip()

            # Déduction du label depuis le prompt
            label = prompt[:48] + ("..." if len(prompt) > 48 else "")

            # Affichage dans la fenêtre visuelle
            self.sig_visual.emit(html, label)

            # Confirmation vocale
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
        READ_ACTIONS = {"browser_read", "get_volume", "get_brightness", "wifi_status"}

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

            # ── Commandes internes ────────────────────────────────────────────
            if user_input.startswith("__CMD__"):
                cmd = user_input.replace("__CMD__", "")
                if cmd == "silent_toggle":
                    user_input = "toggle silent mode"
                else:
                    continue

            # ── Vision ────────────────────────────────────────────────────────
            if user_input.startswith("__VISION__"):
                prompt = user_input.replace("__VISION__", "").strip()
                self._handle_vision(prompt, system, speak_stream_sentences, ask_mara_stream)
                continue

            if "quit" in user_input.lower():
                speak("À bientôt.")
                self._running = False
                break

            if source == "voice":
                self.sig_user_msg.emit(user_input)

            # ── Cerveau ───────────────────────────────────────────────────────
            self.sig_status.emit("THINKING")
            stream = ask_mara_stream(user_input)
            first = next(stream, "")

            # ── Intents spéciaux ──────────────────────────────────────────────
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
                self._handle_vision(prompt, system, speak_stream_sentences, ask_mara_stream)
                self.sig_status.emit("IDLE")
                continue

            if first.startswith("__VISUAL__"):
                prompt = first.replace("__VISUAL__", "").strip()
                self._handle_visual(prompt, speak_stream_sentences)
                continue

            # ── Streaming ─────────────────────────────────────────────────────
            self.sig_stream_start.emit()
            full_response = first
            self.sig_chunk.emit(first)

            for chunk in stream:
                if not self._running:
                    break
                full_response += chunk
                self.sig_chunk.emit(chunk)

            if system.is_paused(memory):
                self.sig_done.emit("", [])
                continue

            # ── Parsing JSON ──────────────────────────────────────────────────
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

            # ── TTS ───────────────────────────────────────────────────────────
            if vocal:
                self.sig_status.emit("SPEAKING")
                if actions:
                    speak_stream_sentences(iter([vocal]))
                else:
                    speak_stream_sentences(iter([full_response]))

            self.sig_status.emit("OPERATIONAL")

            if not actions:
                continue

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
                    continue

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

    def _handle_vision(self, prompt, system, speak_stream_fn, ask_mara_stream):
        try:
            import base64, os, re as _re, json as _json
            from core import system as sys_mod
            from anthropic import Anthropic
            from dotenv import load_dotenv
            load_dotenv()

            result = sys_mod.take_screenshot_for_vision()

            if not result:
                msg = "I can not take a screenshot right now."
                self.sig_done.emit(msg, [])
                print(f"MARA : {msg}")
                return

            self.sig_status.emit("THINKING")

            with open(result, "rb") as f:
                img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

            client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

            from core.brain import _build_system_prompt
            system_prompt = _build_system_prompt()

            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=500,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {
                            "type": "base64", "media_type": "image/png", "data": img_b64
                        }},
                        {"type": "text", "text": prompt or "Describe what you see on this screen."}
                    ]
                }]
            )
            answer = response.content[0].text

            vocal = answer
            actions = []
            try:
                m = _re.search(r'\{.*"actions"\s*:.*\}', answer, _re.DOTALL)
                if m:
                    parsed = _json.loads(m.group())
                    if isinstance(parsed, dict) and "actions" in parsed:
                        vocal = parsed.get("response", answer)
                        actions = parsed.get("actions", [])
            except (_json.JSONDecodeError, AttributeError):
                pass

            chips = [a.get("type", "") for a in actions]
            self.sig_stream_start.emit()
            self.sig_chunk.emit(vocal)
            self.sig_done.emit(vocal, chips)
            print(f"MARA (vision) : {vocal}")

            self.sig_status.emit("SPEAKING")
            speak_stream_fn(iter([vocal]))

            if actions:
                from core.executor import execute
                execute(actions)

            self.sig_status.emit("IDLE")

        except Exception as e:
            msg = f"Vision error : {e}"
            self.sig_done.emit(msg, [])
            self.sig_status.emit("IDLE")
            print(f"MARA : {msg}")

    def stop(self):
        self._running = False
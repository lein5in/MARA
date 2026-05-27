import sys
import re
import json
import time
import queue
import threading
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QScrollArea, QLabel,
    QFrame, QSizePolicy, QDesktopWidget
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QFont

# ─── Palette ──────────────────────────────────────────────────────────────────
BG         = "#0c0c10"
ACCENT     = "#4ecca3"
TEXT_MARA  = "#dcdcd4"
TEXT_YOU   = "#6e6e82"
TEXT_TS    = "#2a2a38"
LABEL_MARA = "#4ecca3"
LABEL_YOU  = "#5a5a6e"
BORDER     = "#1e1e28"
CHIP_TEXT  = "#5a5a6e"

WIN_W  = 520
WIN_H  = 640

def _mono(size: int, bold: bool = False) -> QFont:
    f = QFont("Consolas", size, QFont.Bold if bold else QFont.Normal)
    f.setStyleHint(QFont.Monospace)
    return f

WIN_STYLE = f"""
QWidget {{ background: {BG}; color: {TEXT_MARA}; font-family: Consolas, 'Courier New', monospace; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 4px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #2a2a35; border-radius: 2px; min-height: 20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QLineEdit {{
    background: transparent; border: none;
    color: {TEXT_MARA}; font-family: Consolas, 'Courier New', monospace;
    font-size: 13px; selection-background-color: #2a4a3a;
}}
"""

TB_BTN = f"""
QPushButton {{
    background: transparent; border: 1px solid #2a2a35;
    color: #4a4a58; border-radius: 4px; padding: 0px;
    font-family: Consolas, 'Courier New', monospace; font-size: 13px;
}}
QPushButton:hover {{ border-color: #3a3a48; color: #888; }}
"""

def _mode_btn_style(fs: bool = False) -> str:
    sz = "11px" if fs else "10px"
    pad = "6px 14px" if fs else "4px 11px"
    h = "32px" if fs else "28px"
    return f"""
QPushButton {{
    background: transparent; border: 1px solid #252530;
    color: #44445a; border-radius: 4px; padding: {pad};
    font-family: Consolas, 'Courier New', monospace;
    font-size: {sz}; letter-spacing: 1px; min-height: {h};
}}
QPushButton:hover {{ border-color: #3a3a48; color: #7a7a8e; }}
QPushButton[active="true"] {{
    color: {ACCENT}; border: 1px solid rgba(78,204,163,0.35);
    background: rgba(78,204,163,0.06);
}}
"""

def _send_btn_style(fs: bool = False) -> str:
    sz = "13px" if fs else "12px"
    pad = "11px 26px" if fs else "9px 22px"
    h = "42px" if fs else "38px"
    return f"""
QPushButton {{
    background: {ACCENT}; border: none; color: #0c0c10;
    border-radius: 4px; padding: {pad};
    font-family: Consolas, 'Courier New', monospace;
    font-size: {sz}; font-weight: bold; letter-spacing: 1px;
    min-height: {h};
}}
QPushButton:hover {{ background: #62d4ad; }}
QPushButton:pressed {{ background: #3ab890; }}
"""


# ══════════════════════════════════════════════════════════════════════════════
# WIDGETS
# ══════════════════════════════════════════════════════════════════════════════

class Divider(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setStyleSheet("background: #181820;")


class Chip(QLabel):
    def __init__(self, text: str, fs: bool = False, parent=None):
        super().__init__(parent)
        self.setText(text)
        sz = "11px" if fs else "10px"
        self.setFont(_mono(10 if fs else 9))
        self.setStyleSheet(f"""
            QLabel {{
                color: {CHIP_TEXT}; border: 1px solid #2a2a38;
                border-radius: 3px; padding: 2px 8px;
                font-size: {sz}; letter-spacing: 1px;
            }}
        """)


class MessageEntry(QWidget):
    def __init__(self, who: str, text: str = "", fs: bool = False, parent=None):
        super().__init__(parent)
        self.who = who
        self._fs = fs
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        if who == "MARA":
            bar = QFrame()
            bar.setFixedWidth(2)
            bar.setStyleSheet("background: rgba(78,204,163,0.45); border: none;")
            outer.addWidget(bar)

        content = QWidget()
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        inner = QVBoxLayout(content)
        pad = 18 if fs else 16
        inner.setContentsMargins(pad if who == "MARA" else pad + 2, 10, pad + 2, 10)
        inner.setSpacing(4)

        ts = datetime.now().strftime("%H:%M:%S")
        ts_lbl = QLabel(ts)
        ts_lbl.setFont(_mono(10 if fs else 9))
        ts_lbl.setStyleSheet(f"color: {TEXT_TS}; letter-spacing: 1px;")
        inner.addWidget(ts_lbl)

        who_lbl = QLabel(who)
        who_lbl.setFont(_mono(11 if fs else 10, bold=True))
        col = LABEL_MARA if who == "MARA" else LABEL_YOU
        who_lbl.setStyleSheet(f"color: {col}; letter-spacing: 2px;")
        inner.addWidget(who_lbl)

        self._text_lbl = QLabel(text)
        self._text_lbl.setWordWrap(True)
        self._text_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._text_lbl.setFont(_mono(15 if fs else 13))
        col2 = TEXT_MARA if who == "MARA" else TEXT_YOU
        self._text_lbl.setStyleSheet(f"color: {col2};")
        self._text_lbl.setTextFormat(Qt.PlainText)
        inner.addWidget(self._text_lbl)

        self._chips_row = QHBoxLayout()
        self._chips_row.setSpacing(6)
        self._chips_row.setContentsMargins(0, 4, 0, 0)
        inner.addLayout(self._chips_row)

        outer.addWidget(content)

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
                dot = QLabel("●")
                dot.setFont(_mono(8))
                dot.setStyleSheet(f"color: {ACCENT}; padding: 0; margin: 0;")
                self._chips_row.addWidget(dot)
                self._chips_row.addWidget(Chip(c, fs=self._fs))
        self._chips_row.addStretch()


# ══════════════════════════════════════════════════════════════════════════════
# FENÊTRE PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════════

class MARAWindow(QWidget):
    def __init__(self, text_queue: queue.Queue):
        super().__init__()
        self._text_queue = text_queue
        self._mode = "TEXT"
        self._pending: MessageEntry | None = None
        self._entry_count = 0
        self._drag_pos = None
        self._is_fullscreen = False
        self._normal_geometry = None

        self._setup_window()
        self._build_ui()
        self._setup_pulse()

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
        root.addWidget(self._build_titlebar())
        root.addWidget(self._sep())
        root.addWidget(self._build_log(), stretch=1)
        root.addWidget(self._sep())
        root.addWidget(self._build_input())

    def _build_titlebar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(48)
        bar.setStyleSheet(f"background: {BG};")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(18, 0, 14, 0)
        lay.setSpacing(10)

        self._pulse = QLabel("●")
        self._pulse.setFont(_mono(9))
        self._pulse.setStyleSheet(f"color: {ACCENT};")
        lay.addWidget(self._pulse)

        name = QLabel("MARA")
        name.setFont(_mono(12, bold=True))
        name.setStyleSheet("color: #e0e0d8; letter-spacing: 3px;")
        lay.addWidget(name)

        self._status = QLabel("OPERATIONAL")
        self._status.setFont(_mono(9))
        self._status.setStyleSheet("color: #3a3a50; letter-spacing: 2px;")
        lay.addWidget(self._status)

        lay.addStretch()

        self._silent_btn = QPushButton("⊘")
        self._silent_btn.setFixedSize(30, 30)
        self._silent_btn.setStyleSheet(TB_BTN)
        self._silent_btn.setToolTip("Toggle silent mode")
        self._silent_btn.clicked.connect(self._toggle_silent)
        lay.addWidget(self._silent_btn)

        self._fs_btn = QPushButton("⤢")
        self._fs_btn.setFixedSize(30, 30)
        self._fs_btn.setStyleSheet(TB_BTN)
        self._fs_btn.setToolTip("Fullscreen")
        self._fs_btn.clicked.connect(self._toggle_fullscreen)
        lay.addWidget(self._fs_btn)

        min_btn = QPushButton("−")
        min_btn.setFixedSize(30, 30)
        min_btn.setStyleSheet(TB_BTN)
        min_btn.clicked.connect(self.hide)
        lay.addWidget(min_btn)

        return bar

    def _build_log(self) -> QScrollArea:
        self._log_inner = QWidget()
        self._log_inner.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._log_layout = QVBoxLayout(self._log_inner)
        self._log_layout.setContentsMargins(0, 10, 0, 10)
        self._log_layout.setSpacing(0)
        self._log_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(self._log_inner)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll = scroll
        return scroll

    def _build_input(self) -> QWidget:
        self._input_area = QWidget()
        self._input_area.setStyleSheet(f"background: {BG};")
        lay = QVBoxLayout(self._input_area)
        lay.setContentsMargins(18, 12, 18, 16)
        lay.setSpacing(12)

        cmd = QHBoxLayout()
        cmd.setSpacing(10)
        self._prompt_lbl = QLabel(">_")
        self._prompt_lbl.setFont(_mono(12))
        self._prompt_lbl.setStyleSheet(f"color: {ACCENT};")
        cmd.addWidget(self._prompt_lbl)

        self._input = QLineEdit()
        self._input.setPlaceholderText("type a command...")
        self._input.setFont(_mono(13))
        self._input.returnPressed.connect(self._send)
        cmd.addWidget(self._input)
        lay.addLayout(cmd)

        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        self._mode_btns: dict[str, QPushButton] = {}
        for m in ["TEXT", "SILENT", "VISION"]:
            btn = QPushButton(m)
            btn.setFont(_mono(10))
            btn.setStyleSheet(_mode_btn_style(False))
            btn.setFixedHeight(28)
            btn.setProperty("active", m == "TEXT")
            btn.clicked.connect(lambda _, mode=m: self._set_mode(mode))
            self._mode_btns[m] = btn
            bottom.addWidget(btn)

        bottom.addStretch()

        self._send_btn = QPushButton("SEND ↵")
        self._send_btn.setFont(_mono(11, bold=True))
        self._send_btn.setStyleSheet(_send_btn_style(False))
        self._send_btn.setFixedHeight(38)
        self._send_btn.clicked.connect(self._send)
        bottom.addWidget(self._send_btn)

        lay.addLayout(bottom)
        return self._input_area

    def _setup_pulse(self):
        self._pulse_state = True
        self._pulse_timer = QTimer()
        self._pulse_timer.timeout.connect(self._tick_pulse)
        self._pulse_timer.start(1400)

    def _tick_pulse(self):
        self._pulse_state = not self._pulse_state
        col = ACCENT if self._pulse_state else "#1a4a3a"
        self._pulse.setStyleSheet(f"color: {col};")

    def _sep(self) -> QFrame:
        f = QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet(f"background: {BORDER};")
        return f

    def _insert_widget(self, widget: QWidget):
        idx = self._log_layout.count() - 1
        self._log_layout.insertWidget(idx, widget)

    def _add_entry(self, entry: MessageEntry):
        if self._entry_count > 0:
            self._insert_widget(Divider())
        self._insert_widget(entry)
        self._entry_count += 1
        self._scroll_bottom()

    def _scroll_bottom(self):
        QTimer.singleShot(60, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    def _refresh_mode_btn(self, btn: QPushButton):
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    # ── Slots publics ─────────────────────────────────────────────────────────

    def on_status(self, status: str):
        self._status.setText(status)

    def on_mara_stream_start(self):
        if self._pending:
            return
        entry = MessageEntry("MARA", fs=self._is_fullscreen)
        self._add_entry(entry)
        self._pending = entry

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
            entry = MessageEntry("MARA", vocal, fs=self._is_fullscreen)
            self._add_entry(entry)
        self._scroll_bottom()

    def on_user_message(self, text: str):
        entry = MessageEntry("YOU", text, fs=self._is_fullscreen)
        self._add_entry(entry)

    def on_password_mode(self, active: bool):
        if active:
            self._input.setEchoMode(QLineEdit.Password)
            self._input.setPlaceholderText("enter password (hidden)...")
            self._input.setFocus()
        else:
            self._input.setEchoMode(QLineEdit.Normal)
            self._input.setPlaceholderText("type a command...")

    # ── Actions UI ────────────────────────────────────────────────────────────

    def _toggle_fullscreen(self):
        if not self._is_fullscreen:
            self._normal_geometry = self.geometry()
            self.setWindowFlags(Qt.FramelessWindowHint)
            screen = QDesktopWidget().screenGeometry()
            self.setGeometry(screen)
            self._fs_btn.setText("⤡")
            self._is_fullscreen = True
            # Scale les boutons
            for btn in self._mode_btns.values():
                btn.setStyleSheet(_mode_btn_style(True))
                btn.setFixedHeight(32)
            self._send_btn.setStyleSheet(_send_btn_style(True))
            self._send_btn.setFixedHeight(42)
            self._prompt_lbl.setFont(_mono(14))
            self._input.setFont(_mono(15))
        else:
            self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
            if self._normal_geometry:
                self.setGeometry(self._normal_geometry)
            self._fs_btn.setText("⤢")
            self._is_fullscreen = False
            # Restore les boutons
            for btn in self._mode_btns.values():
                btn.setStyleSheet(_mode_btn_style(False))
                btn.setFixedHeight(28)
            self._send_btn.setStyleSheet(_send_btn_style(False))
            self._send_btn.setFixedHeight(38)
            self._prompt_lbl.setFont(_mono(12))
            self._input.setFont(_mono(13))
        self.show()

    def _set_mode(self, mode: str):
        self._mode = mode
        for m, btn in self._mode_btns.items():
            btn.setProperty("active", m == mode)
            self._refresh_mode_btn(btn)

    def _toggle_silent(self):
        self._text_queue.put("__CMD__silent_toggle")
        active = self._silent_btn.property("silent_on")
        self._silent_btn.setProperty("silent_on", not active)
        col = ACCENT if not active else "#4a4a58"
        self._silent_btn.setStyleSheet(TB_BTN + f"\nQPushButton {{ color: {col}; }}")

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

    _PWD_KW  = {"password", "mot de passe", "كلمة المرور", "pass"}
    _OFFLINE = {
        "fr": "Système en pause. Maintiens ENTRÉE et dis mon nom pour me réveiller.",
        "en": "System offline. Hold Enter and say my name to wake me.",
        "ar": "النظام في وضع الإيقاف. اضغط Enter وقل اسمي لإيقاظي.",
    }
    _WAKE = {"mara"}

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

    def run(self):
        from core.brain import ask_mara_stream, get_work_mode_ask, get_work_mode_launch
        from core.listener import listen
        from core.voice import speak, speak_stream
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
                self._handle_vision(prompt, system, speak_stream, ask_mara_stream)
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
                self._handle_work_mode(language, speak_stream, execute,
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
                speak_stream(iter([msg]))
                self.sig_status.emit("OPERATIONAL")
                continue

            if first.startswith("__UI_HIDE__"):
                language = first.replace("__UI_HIDE__", "").strip() or "en"
                from core.brain import MEMORY_RESPONSES
                msg = MEMORY_RESPONSES["ui_hide"].get(language, "Going dark.")
                self.sig_done.emit(msg, [])
                print(f"MARA : {msg}")
                speak_stream(iter([msg]))
                self.sig_hide.emit()
                self.sig_status.emit("OPERATIONAL")
                continue

            # ── Streaming temps réel ──────────────────────────────────────────
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

            # ── Print terminal ────────────────────────────────────────────────
            print(f"MARA : {vocal or full_response}")

            # ── TTS ───────────────────────────────────────────────────────────
            if vocal:
                self.sig_status.emit("SPEAKING")
                speak_stream(iter([vocal]))

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
                    speak_stream(iter([sr]))
                    self.sig_status.emit("OPERATIONAL")

                elif atype in READ_ACTIONS and result and not result.startswith("Erreur"):
                    self.sig_done.emit(result, [])
                    print(f"MARA ({atype}) : {result}")
                    self.sig_status.emit("SPEAKING")
                    speak_stream(iter([result]))
                    self.sig_status.emit("OPERATIONAL")

                elif atype == "pause" and result:
                    self.sig_done.emit(result, [])
                    print(f"MARA (pause) : {result}")
                    speak_stream(iter([result]))

                elif atype in ("silent_on", "silent_off") and result:
                    self.sig_done.emit(result, [])
                    print(f"MARA ({atype}) : {result}")
                    speak_stream(iter([result]))

    def _handle_vision(self, prompt, system, speak_stream, ask_mara_stream):
        try:
            import base64, os
            from core import system as sys_mod
            from anthropic import Anthropic
            from dotenv import load_dotenv
            load_dotenv()

            result = sys_mod.take_screenshot()
            if not result or result.startswith("Erreur"):
                msg = "Je n'arrive pas à prendre le screenshot."
                self.sig_done.emit(msg, [])
                print(f"MARA : {msg}")
                return

            self.sig_status.emit("THINKING")
            with open(result, "rb") as f:
                img_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

            client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=500,
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
            self.sig_stream_start.emit()
            self.sig_chunk.emit(answer)
            self.sig_done.emit(answer, [])
            print(f"MARA (vision) : {answer}")
            self.sig_status.emit("SPEAKING")
            speak_stream(iter([answer]))
            self.sig_status.emit("OPERATIONAL")

        except Exception as e:
            msg = f"Vision error: {e}"
            self.sig_done.emit(msg, [])
            print(f"MARA : {msg}")

    def stop(self):
        self._running = False
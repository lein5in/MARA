import math
from datetime import datetime

from PyQt5.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt5.QtGui import QTextDocument, QGuiApplication
from PyQt5.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout, QFrame, QPushButton, QSizePolicy, QGraphicsOpacityEffect,
)

from core.text import split_fences, code_lines, copyable_code
from core.ui import theme
from core.ui.theme import C

USER_MAX = 470
REPLY_MAX = 560
BLOCK_MAX = 580


def hbox(*widgets, spacing=0, margins=(0, 0, 0, 0)) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for w in widgets:
        if w is None:
            lay.addStretch(1)
        elif isinstance(w, int):
            lay.addSpacing(w)
        else:
            lay.addWidget(w)
    return lay


def label(text: str, name: str, f=None, rich: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName(name)
    lbl.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    if f is not None:
        lbl.setFont(f)
    return lbl


def icon_label(name: str, color: str, size: int, stroke: float = 1.6) -> QLabel:
    lbl = QLabel()
    lbl.setFixedSize(size, size)
    lbl.setPixmap(theme.icon_pixmap(name, color, size, stroke))
    return lbl


class WrapLabel(QLabel):
    def __init__(self, name: str, f, max_width: int, line_height: int = 132):
        super().__init__()
        self.setObjectName(name)
        self.setFont(f)
        self.setTextFormat(Qt.RichText)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.setCursor(Qt.IBeamCursor)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self._max = max_width
        self._line_height = line_height
        self._cache = {}

    def set_inner(self, inner_html: str):
        self._cache = {}
        self.setText(theme.text_html(inner_html, self._line_height))
        self.updateGeometry()

    def _measure(self, width: float | None):
        key = width
        if key not in self._cache:
            doc = QTextDocument()
            doc.setDefaultFont(self.font())
            doc.setDocumentMargin(0)
            doc.setHtml(self.text())
            if width is None:
                ideal = math.ceil(doc.idealWidth()) + 2
                width = min(ideal, self._max)
            doc.setTextWidth(width)
            self._cache[key] = (int(width), math.ceil(doc.size().height()))
        return self._cache[key]

    def sizeHint(self):
        w, h = self._measure(None)
        return QSize(w, h)

    def minimumSizeHint(self):
        return QSize(40, self._measure(None)[1])

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._measure(min(width, self._max))[1]


class DaySeparator(QWidget):
    def __init__(self, text: str):
        super().__init__()
        lines = []
        for _ in range(2):
            line = QFrame()
            line.setObjectName("DayLine")
            line.setFixedHeight(1)
            line.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            lines.append(line)
        lbl = label(text, "Meta", theme.mono(11, spacing_em=0.04))
        self.setLayout(hbox(lines[0], lbl, lines[1], spacing=14))


def stamp(when: datetime | None = None) -> str:
    return (when or datetime.now()).strftime("%H:%M")


class UserBlock(QWidget):
    def __init__(self, text: str, source: str = "typed", live: bool = False):
        super().__init__()
        self.source = source
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(7)

        meta_items = []
        if source == "voice":
            meta_items.append(icon_label("mic", C["dim"], 12))
        self._meta = label("", "Meta", theme.mono(11))
        meta_items.append(self._meta)
        outer.addLayout(hbox(None, *meta_items, spacing=7))

        self.bubble = QFrame()
        self.bubble.setObjectName("UserBubble")
        self.bubble.setMaximumWidth(USER_MAX)
        prompt = label("›", "Prompt", theme.mono(14.5))
        prompt.setAlignment(Qt.AlignTop)
        self.text = WrapLabel("UserText", theme.body(14.5), USER_MAX - 28 - 20, line_height=128)
        lay = hbox(prompt, self.text, spacing=10, margins=(14, 11, 14, 11))
        lay.setAlignment(prompt, Qt.AlignTop)
        self.bubble.setLayout(lay)
        outer.addLayout(hbox(None, self.bubble))

        self._raw = ""
        self.cursor_on = False
        self.set_live(live)
        self.set_text(text)

    def set_live(self, live: bool):
        self.live = live
        self.cursor_on = live
        self.bubble.setProperty("live", live)
        self.bubble.style().unpolish(self.bubble)
        self.bubble.style().polish(self.bubble)
        if live:
            self._meta.setText("you · transcribing live")
        else:
            self._meta.setText(f"you · {self.source} · {stamp()}")

    def set_text(self, text: str):
        self._raw = text
        self._render()

    def set_cursor(self, on: bool):
        self.cursor_on = on
        self._render()

    def _render(self):
        inner = theme.esc(self._raw).replace("\n", "<br>")
        if self.live:
            inner += theme.cursor_html(self.cursor_on)
        self.text.set_inner(inner or "&nbsp;")


class ReceiptRow(QWidget):
    def __init__(self, name: str, args: str):
        super().__init__()
        self.icon = QLabel()
        self.icon.setFixedSize(14, 14)
        self.name = label(name, "ReceiptName", theme.mono(12))
        self.args = label(args, "ReceiptArgs", theme.mono(12))
        self.args.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.args.setToolTip(args)
        self.time = label("", "ReceiptTime", theme.mono(12))
        lay = hbox(self.icon, self.name, self.args, self.time, spacing=10, margins=(14, 9, 14, 9))
        lay.setStretch(2, 1)
        self.setLayout(lay)
        self.set_running()

    def set_running(self):
        self.icon.setPixmap(theme.icon_pixmap("dots", C["dim"], 14, 2.6))

    def set_finished(self, ok: bool, duration: float, summary: str = ""):
        self.icon.setPixmap(theme.icon_pixmap("check" if ok else "cross", C["accent"] if ok else C["removed"], 14, 2.2))
        self.name.setProperty("failed", not ok)
        self.name.style().unpolish(self.name)
        self.name.style().polish(self.name)
        self.time.setText(f"{duration:.1f}s")
        if summary:
            self.setToolTip(summary)


class Receipts(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Receipts")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)
        self.rows: dict[str, ReceiptRow] = {}
        self.hide()

    def start(self, tid: str, name: str, args: str):
        if self.rows:
            sep = QFrame()
            sep.setObjectName("ReceiptSep")
            sep.setFixedHeight(1)
            self._lay.addWidget(sep)
        row = ReceiptRow(name, args)
        self.rows[tid] = row
        self._lay.addWidget(row)
        self.show()

    def finish(self, tid: str, name: str, ok: bool, duration: float, summary: str):
        if tid not in self.rows:
            self.start(tid, name, "")
        self.rows[tid].set_finished(ok, duration, summary)

    def drop(self, tid: str):
        row = self.rows.pop(tid, None)
        if row is None:
            return
        idx = self._lay.indexOf(row)
        if idx > 0:
            sep = self._lay.itemAt(idx - 1).widget()
            self._lay.removeWidget(sep)
            sep.deleteLater()
        elif idx == 0 and self._lay.count() > 1:
            sep = self._lay.itemAt(1).widget()
            self._lay.removeWidget(sep)
            sep.deleteLater()
        self._lay.removeWidget(row)
        row.deleteLater()
        self.setVisible(bool(self.rows))


class CodeBlock(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("CodeBlock")
        self.setMaximumWidth(BLOCK_MAX)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        header = QFrame()
        header.setObjectName("CodeHeader")
        header.setFixedHeight(34)
        self.lang = label("", "CodeLang", theme.mono(11.5))
        self.copy_btn = QPushButton(" copy")
        self.copy_btn.setObjectName("CopyButton")
        self.copy_btn.setFont(theme.mono(11.5))
        self.copy_btn.setIcon(theme.icon("copy", C["tertiary"], 13, 1.7))
        self.copy_btn.setIconSize(QSize(13, 13))
        self.copy_btn.setFixedHeight(24)
        self.copy_btn.setCursor(Qt.PointingHandCursor)
        self.copy_btn.clicked.connect(self.copy)
        header.setLayout(hbox(self.lang, None, self.copy_btn, margins=(14, 0, 8, 0)))
        outer.addWidget(header)

        self.body = QLabel()
        self.body.setObjectName("CodeBody")
        self.body.setFont(theme.mono(12.5))
        self.body.setTextFormat(Qt.RichText)
        self.body.setWordWrap(True)
        self.body.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.body.setContentsMargins(0, 10, 0, 10)
        outer.addWidget(self.body)
        self._code = ""
        self._diff = False
        self._key = None

    def set_code(self, lang: str, code: str, diff: bool):
        key = (lang, code, diff)
        if key == self._key:
            return
        self._key = key
        self._code, self._diff = code, diff
        name = lang or "code"
        self.lang.setText(f"{name} · suggested fix" if diff else name)
        rows = []
        for n, marker, content in code_lines(code, diff):
            if marker == "-":
                bg, mark_color, text = C["removed_bg"], C["removed"], f'<span style="color:{C["removed_text"]};">{theme.code_text(content)}</span>'
            elif marker == "+":
                bg, mark_color, text = C["added_bg"], C["added"], f'<span style="color:{C["added_text"]};">{theme.code_text(content)}</span>'
            else:
                bg, mark_color, text = None, C["line_no"], theme.highlight(content, lang)
            sign = {"-": "−", "+": "+"}.get(marker, "")
            row_bg = f' bgcolor="{bg}"' if bg else ""
            rows.append(
                f'<tr{row_bg}><td width="14"></td>'
                f'<td width="28" style="color:{C["line_no"]};">{n}</td>'
                f'<td width="16" style="color:{mark_color};">{sign}</td>'
                f'<td>{text or "&nbsp;"}</td><td width="14"></td></tr>'
            )
        self.body.setText(
            '<table width="100%" cellspacing="0" cellpadding="2" style="line-height:112%;">'
            + "".join(rows) + "</table>"
        )

    def copy(self):
        QGuiApplication.clipboard().setText(copyable_code(self._code, self._diff))
        self.copy_btn.setText(" copied")
        self.copy_btn.setIcon(theme.icon("check", C["accent"], 13, 2.0))
        QTimer.singleShot(1500, self._reset_copy)

    def _reset_copy(self):
        self.copy_btn.setText(" copy")
        self.copy_btn.setIcon(theme.icon("copy", C["tertiary"], 13, 1.7))


class ReplyView(QWidget):
    def __init__(self):
        super().__init__()
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(10)
        self._widgets: list[QWidget] = []
        self._kinds: list[str] = []
        self._rendered: list = []
        self.raw = ""
        self.streaming = False
        self.cursor_on = False

    def append(self, delta: str):
        self.raw += delta
        self.render()

    def set_streaming(self, on: bool):
        self.streaming = on
        self.render()

    def set_cursor(self, on: bool):
        self.cursor_on = on
        if self._kinds and self._kinds[-1] == "text":
            self._rendered[-1] = None
            self.render()

    def render(self):
        segments = split_fences(self.raw) if self.raw.strip() else []
        if self.streaming and (not segments or segments[-1]["kind"] == "code"):
            segments = segments + [{"kind": "text", "text": ""}]
        for i, seg in enumerate(segments):
            if i < len(self._widgets) and self._kinds[i] != seg["kind"]:
                self._drop_from(i)
            if i >= len(self._widgets):
                w = WrapLabel("ReplyText", theme.body(14.5), REPLY_MAX) if seg["kind"] == "text" else CodeBlock()
                self._lay.addWidget(w)
                self._widgets.append(w)
                self._kinds.append(seg["kind"])
                self._rendered.append(None)
            last = i == len(segments) - 1
            if seg["kind"] == "text":
                key = (seg["text"], last and self.streaming and self.cursor_on, last and self.streaming)
                if self._rendered[i] != key:
                    inner = theme.inline_markdown(seg["text"])
                    if last and self.streaming:
                        inner += theme.cursor_html(self.cursor_on)
                    self._widgets[i].set_inner(inner or "&nbsp;")
                    self._widgets[i].setVisible(bool(inner))
                    self._rendered[i] = key
            else:
                self._widgets[i].set_code(seg["lang"], seg["code"], seg["diff"])
        self._drop_from(len(segments))
        self.setVisible(bool(self._widgets))

    def _drop_from(self, index: int):
        for w in self._widgets[index:]:
            self._lay.removeWidget(w)
            w.hide()
            w.deleteLater()
        del self._widgets[index:], self._kinds[index:], self._rendered[index:]

    def code_blocks(self) -> list[CodeBlock]:
        return [w for w in self._widgets if isinstance(w, CodeBlock)]


class ConfirmCard(QFrame):
    answered = pyqtSignal(str, bool)

    def __init__(self, cid: str, title: str, description: str, tool: str, args: str):
        super().__init__()
        self.cid = cid
        self.setObjectName("Confirm")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        warn = QFrame()
        warn.setObjectName("WarnIcon")
        warn.setFixedSize(32, 32)
        warn.setLayout(hbox(icon_label("warn", C["warn"], 17, 1.7), margins=(7, 7, 7, 7)))
        texts = QVBoxLayout()
        texts.setSpacing(6)
        texts.addWidget(label(title, "ConfirmTitle", theme.body(14, 600)))
        desc = WrapLabel("ConfirmDesc", theme.body(13), 440, line_height=124)
        desc.set_inner(theme.esc(description))
        texts.addWidget(desc)
        top = QHBoxLayout()
        top.setContentsMargins(18, 16, 18, 16)
        top.setSpacing(14)
        top.addWidget(warn, 0, Qt.AlignTop)
        top.addLayout(texts, 1)
        outer.addLayout(top)

        tool_row = QFrame()
        tool_row.setObjectName("ConfirmTool")
        args_lbl = label(args, "ConfirmToolArgs", theme.mono(12))
        args_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        tool_row.setLayout(hbox(label(tool, "ConfirmToolName", theme.mono(12)), None, args_lbl,
                                spacing=12, margins=(18, 10, 18, 10)))
        outer.addWidget(tool_row)

        foot = QFrame()
        foot.setObjectName("ConfirmFoot")
        self.hint = label("You can also say “yes” or “cancel”.", "ConfirmHint", theme.body(12))
        self.cancel_btn = QPushButton("cancel")
        self.cancel_btn.setObjectName("GhostButton")
        self.confirm_btn = QPushButton(title.split()[0].lower() if title else "confirm")
        self.confirm_btn.setObjectName("WarnButton")
        for btn in (self.cancel_btn, self.confirm_btn):
            btn.setFont(theme.mono(12.5, 600 if btn is self.confirm_btn else 500))
            btn.setFixedHeight(34)
            btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(lambda: self.answered.emit(self.cid, False))
        self.confirm_btn.clicked.connect(lambda: self.answered.emit(self.cid, True))
        foot.setLayout(hbox(self.hint, None, self.cancel_btn, 10, self.confirm_btn, margins=(18, 14, 18, 14)))
        outer.addWidget(foot)

    def resolve(self, accepted: bool):
        self.cancel_btn.setEnabled(False)
        self.confirm_btn.setEnabled(False)
        self.hint.setText("confirmed" if accepted else "cancelled")


class MaraBlock(QWidget):
    confirm_answered = pyqtSignal(str, bool)

    def __init__(self):
        super().__init__()
        self.setMaximumWidth(REPLY_MAX)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(9)
        name = label("mara", "MetaName", theme.mono(11, 600))
        lay.addLayout(hbox(name, label(stamp(), "Meta", theme.mono(11)), None, spacing=8))
        self.receipts = Receipts()
        lay.addWidget(self.receipts)
        self.reply = ReplyView()
        self.reply.hide()
        lay.addWidget(self.reply)
        self.error = WrapLabel("ErrorText", theme.mono(12.5), REPLY_MAX, line_height=124)
        self.error.hide()
        lay.addWidget(self.error)
        self._lay = lay
        self.cards: dict[str, ConfirmCard] = {}

    def append_text(self, delta: str):
        if not self.reply.streaming:
            self.reply.streaming = True
            self.reply.cursor_on = True
        self.reply.append(delta)
        if self.reply.code_blocks():
            self.setMaximumWidth(BLOCK_MAX)

    def finish(self):
        self.reply.set_streaming(False)

    def set_cursor(self, on: bool):
        self.reply.set_cursor(on)

    def show_error(self, message: str):
        self.error.set_inner(theme.esc(message))
        self.error.show()

    def add_confirmation(self, cid, title, description, tool, args) -> ConfirmCard:
        card = ConfirmCard(cid, title, description, tool, args)
        card.answered.connect(self.confirm_answered)
        self.cards[cid] = card
        self._lay.addWidget(card)
        return card

    def sizeHint(self):
        hint = super().sizeHint()
        return QSize(self.maximumWidth(), hint.height())

    def is_empty(self) -> bool:
        return not self.receipts.rows and not self.reply.raw.strip() and self.error.isHidden() and not self.cards


def dim(widget: QWidget, on: bool):
    if on:
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.6)
        widget.setGraphicsEffect(effect)
    else:
        widget.setGraphicsEffect(None)

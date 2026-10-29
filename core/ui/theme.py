import html
import re

from PyQt5.QtCore import Qt, QByteArray, QSize
from PyQt5.QtGui import QFont, QFontDatabase, QIcon, QPixmap, QPainter, QColor
from PyQt5.QtSvg import QSvgRenderer

from core.config import PROJECT_ROOT
from core.log import get_logger
log = get_logger(__name__)

C = {
    "ground": "#0F141D",
    "surface": "#151B26",
    "composer": "#131925",
    "panel": "#0B0F16",
    "hairline": "#232B3A",
    "hairline_soft": "#1D2431",
    "row_sep": "#1A2130",
    "control": "#2A3345",
    "control_strong": "#2F394D",
    "text": "#E6E9EF",
    "secondary": "#B4BCCB",
    "tertiary": "#9AA3B5",
    "dim": "#8892A6",
    "line_no": "#5C667A",
    "code_text": "#D5DAE3",
    "accent": "#E8A0B4",
    "on_accent": "#1A0E14",
    "warn": "#E5B567",
    "on_warn": "#1B1405",
    "warn_bg": "#2A2314",
    "removed": "#F08A8A",
    "removed_text": "#F2A3A3",
    "removed_bg": "#221B22",
    "added": "#7FD1A8",
    "added_text": "#A2E0C1",
    "added_bg": "#172225",
    "kw": "#E8A0B4",
    "str": "#E5B567",
    "num": "#9DB4C0",
    "comment": "#5C667A",
}

BODY = "Inter"
MONO = "JetBrains Mono"
_FALLBACK_BODY = "Segoe UI"
_FALLBACK_MONO = "Consolas"
FONTS_DIR = PROJECT_ROOT / "assets" / "fonts"


def load_fonts():
    global BODY, MONO
    families = set()
    for path in sorted(FONTS_DIR.glob("*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            log.warning(f"[Theme] Could not load font {path.name}")
            continue
        families.update(QFontDatabase.applicationFontFamilies(font_id))
    if "Inter" not in families:
        BODY = _FALLBACK_BODY
        log.warning(f"[Theme] Inter not available, using {BODY}")
    if "JetBrains Mono" not in families:
        MONO = _FALLBACK_MONO
        log.warning(f"[Theme] JetBrains Mono not available, using {MONO}")


def pt(px: float) -> float:
    return px * 0.75


_WEIGHTS = {400: QFont.Normal, 500: QFont.Medium, 600: QFont.DemiBold}


def font(family: str, px: float, weight: int = 400, spacing_em: float = 0.0) -> QFont:
    f = QFont(family)
    f.setPointSizeF(pt(px))
    f.setWeight(_WEIGHTS.get(weight, QFont.Normal))
    if spacing_em:
        f.setLetterSpacing(QFont.AbsoluteSpacing, px * spacing_em)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f


def mono(px: float, weight: int = 400, spacing_em: float = 0.0) -> QFont:
    return font(MONO, px, weight, spacing_em)


def body(px: float, weight: int = 400) -> QFont:
    return font(BODY, px, weight)


def apply(app):
    load_fonts()
    app.setFont(body(14))
    app.setStyleSheet(build_qss())
    app.setWindowIcon(app_icon())


def build_qss() -> str:
    m = f"'{MONO}'"
    return f"""
QWidget {{ color: {C['text']}; }}
QToolTip {{ background: {C['surface']}; color: {C['text']}; border: 1px solid {C['hairline']}; font-family: {m}; }}
#Root {{ background: {C['ground']}; border: 1px solid {C['hairline']}; border-radius: 12px; }}
#Header {{ background: transparent; border-bottom: 1px solid {C['hairline_soft']}; }}
#Header[listening="true"] {{ border-bottom: none; }}
#Monogram {{ border: 1px solid {C['accent']}; border-radius: 6px; color: {C['accent']}; font-family: {m}; font-weight: 600; }}
#Wordmark {{ color: {C['text']}; }}
#StatusText {{ color: {C['dim']}; font-family: {m}; }}
#StatusText[active="true"] {{ color: {C['secondary']}; }}
#IconButton {{ background: transparent; border: none; border-radius: 6px; }}
#IconButton:hover {{ background: {C['surface']}; }}
#ListenBar {{ background: {C['accent']}; }}
#Thread, #ThreadInner {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 6px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {C['control']}; border-radius: 2px; min-height: 30px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
#Meta {{ color: {C['dim']}; font-family: {m}; }}
#MetaName {{ color: {C['accent']}; font-family: {m}; font-weight: 600; }}
#DayLine {{ background: {C['hairline_soft']}; }}
#UserBubble {{ background: {C['surface']}; border: 1px solid {C['hairline']}; border-radius: 6px; }}
#UserBubble[live="true"] {{ border: 1px solid {C['accent']}; }}
#Prompt {{ color: {C['accent']}; font-family: {m}; }}
#UserText, #ReplyText {{ color: {C['text']}; background: transparent; }}
#ErrorText {{ color: {C['removed_text']}; font-family: {m}; }}
#Receipts {{ background: {C['panel']}; border: 1px solid {C['hairline']}; border-radius: 6px; }}
#ReceiptSep {{ background: {C['row_sep']}; }}
#ReceiptName {{ color: {C['secondary']}; font-family: {m}; }}
#ReceiptArgs, #ReceiptTime {{ color: {C['dim']}; font-family: {m}; }}
#ScreenThumb {{ border: 1px solid {C['control_strong']}; border-radius: 3px; background: {C['ground']}; }}
#ThumbLine {{ background: {C['control_strong']}; }}
#ThumbLineAccent {{ background: {C['accent']}; }}
#ReceiptName[failed="true"] {{ color: {C['removed_text']}; }}
#CodeBlock {{ background: {C['panel']}; border: 1px solid {C['hairline']}; border-radius: 6px; }}
#CodeHeader {{ background: {C['composer']}; border: none; border-bottom: 1px solid {C['hairline']};
    border-top-left-radius: 6px; border-top-right-radius: 6px; }}
#CodeLang {{ color: {C['dim']}; font-family: {m}; }}
#CopyButton {{ background: transparent; border: none; border-radius: 4px; color: {C['tertiary']}; font-family: {m}; padding: 0 8px; }}
#CopyButton:hover {{ background: {C['surface']}; color: {C['text']}; }}
#CodeBody {{ background: transparent; color: {C['code_text']}; }}
#Confirm {{ background: {C['composer']}; border: 1px solid {C['control']}; border-radius: 8px; }}
#WarnIcon {{ background: {C['warn_bg']}; border-radius: 6px; }}
#ConfirmTitle {{ color: {C['text']}; }}
#ConfirmDesc {{ color: {C['tertiary']}; }}
#ConfirmTool {{ background: {C['panel']}; border: none; border-top: 1px solid {C['hairline']}; }}
#ConfirmToolName {{ color: {C['dim']}; font-family: {m}; }}
#ConfirmToolArgs {{ color: {C['text']}; font-family: {m}; }}
#ConfirmFoot {{ background: transparent; border: none; border-top: 1px solid {C['hairline']}; }}
#ConfirmHint {{ color: {C['dim']}; }}
#GhostButton {{ background: transparent; border: 1px solid {C['control_strong']}; border-radius: 6px; color: {C['text']};
    font-family: {m}; font-weight: 500; padding: 0 16px; }}
#GhostButton:hover {{ background: {C['surface']}; }}
#WarnButton {{ background: {C['warn']}; border: none; border-radius: 6px; color: {C['on_warn']}; font-family: {m};
    font-weight: 600; padding: 0 16px; }}
#WarnButton:hover {{ background: #EDC27B; }}
#GhostButton:disabled, #WarnButton:disabled {{ background: transparent; border: 1px solid {C['hairline']}; color: {C['line_no']}; }}
#Composer {{ background: {C['composer']}; border: 1px solid {C['control']}; border-radius: 8px; }}
#Composer[locked="true"] {{ border: 1px solid {C['control']}; }}
#ComposerPrompt {{ color: {C['accent']}; font-family: {m}; font-weight: 600; }}
#ComposerPrompt[locked="true"] {{ color: {C['dim']}; }}
#Input {{ background: transparent; border: none; color: {C['text']}; font-family: {m};
    selection-background-color: {C['accent']}; selection-color: {C['on_accent']}; }}
#SendButton {{ background: {C['accent']}; border: none; border-radius: 6px; color: {C['on_accent']}; font-family: {m};
    font-weight: 600; padding: 0 14px; }}
#SendButton:hover {{ background: #EEB3C3; }}
#SendButton:disabled {{ background: {C['control']}; color: {C['dim']}; }}
#ListenStrip {{ background: {C['composer']}; border: 1px solid {C['accent']}; border-radius: 8px; }}
#MicBox {{ background: {C['accent']}; border-radius: 6px; }}
#RecTime {{ color: {C['text']}; font-family: {m}; }}
#RecHint {{ color: {C['dim']}; font-family: {m}; }}
#Toggle {{ background: transparent; border: 1px solid {C['hairline']}; border-radius: 6px; color: {C['tertiary']};
    font-family: {m}; padding: 0 11px; text-align: left; }}
#Toggle:hover {{ border: 1px solid {C['control_strong']}; color: {C['text']}; }}
#Toggle:checked {{ background: {C['surface']}; border: 1px solid {C['accent']}; color: {C['text']}; }}
#Hint {{ color: {C['dim']}; font-family: {m}; }}
#KeyCap {{ border: 1px solid {C['control_strong']}; border-radius: 4px; color: {C['secondary']}; font-family: {m}; padding: 0 7px; }}
#KeyCap[active="true"] {{ border: 1px solid {C['accent']}; color: {C['text']}; }}
#VisualRoot {{ background: {C['ground']}; border: 1px solid {C['hairline']}; border-radius: 12px; }}
#VisualTitle {{ color: {C['secondary']}; font-family: {m}; }}
QMenu {{ background: {C['surface']}; color: {C['text']}; border: 1px solid {C['hairline']}; font-family: {m}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {C['control']}; }}
QMenu::separator {{ height: 1px; background: {C['hairline']}; margin: 4px 6px; }}
"""


ICONS = {
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "expand": '<path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/>',
    "minus": '<path d="M5 12h14"/>',
    "mic": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0014 0M12 18v3"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "cross": '<path d="M6 6l12 12M18 6L6 18"/>',
    "dots": '<path d="M6 12h.01M12 12h.01M18 12h.01"/>',
    "copy": '<rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V6a2 2 0 00-2-2H6a2 2 0 00-2 2v8a2 2 0 002 2h2"/>',
    "warn": '<path d="M12 3l9.5 17h-19L12 3z"/><path d="M12 10v4.5M12 17.2v.1"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
}


def icon_pixmap(name: str, color: str, size: int, stroke: float = 1.6, ratio: float = 2.0) -> QPixmap:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pm = QPixmap(QSize(int(size * ratio), int(size * ratio)))
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, color: str, size: int, stroke: float = 1.6) -> QIcon:
    return QIcon(icon_pixmap(name, color, size, stroke))


def app_icon(size: int = 64) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor(C["accent"]))
    p.setBrush(QColor(C["ground"]))
    p.drawRoundedRect(2, 2, size - 4, size - 4, size * 0.18, size * 0.18)
    f = QFont(MONO)
    f.setPixelSize(int(size * 0.42))
    f.setWeight(QFont.DemiBold)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "›_")
    p.end()
    return QIcon(pm)


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def inline_markdown(text: str) -> str:
    out = []
    for i, part in enumerate(re.split(r"(`[^`\n]+`)", text)):
        if i % 2:
            out.append(f'<span style="font-family:\'{MONO}\'; font-size:{pt(13):.2f}pt; background:{C["surface"]}; '
                       f'color:{C["text"]};">&nbsp;{esc(part[1:-1])}&nbsp;</span>')
        else:
            seg = esc(part)
            seg = re.sub(r"\*\*(.+?)\*\*", r'<span style="font-weight:600;">\1</span>', seg)
            out.append(seg)
    return "".join(out).replace("\n", "<br>")


def text_html(inner: str, line_height: int = 132) -> str:
    return f'<div style="line-height:{line_height}%;">{inner}</div>'


def cursor_html(visible: bool) -> str:
    color = C["accent"] if visible else "transparent"
    return f'<span style="background:{color}; color:{color};">&nbsp;&nbsp;</span>'


KEYWORDS = set("""
and as assert async await break class continue def del elif else except finally for from global if import in is
lambda nonlocal not or pass raise return try while with yield None True False self
function const let var new this typeof instanceof switch case default throw catch void delete extends super export
public private protected static final int float double char bool boolean string struct enum interface package
null true false fn mut impl pub use match loop go func defer type map chan
""".split())

_TOKEN = re.compile(
    r"(?P<comment>#.*$|//.*$)|(?P<str>\"(?:\\.|[^\"\\])*\"?|'(?:\\.|[^'\\])*'?)|(?P<num>\b\d+(?:\.\d+)?\b)|(?P<word>\b[A-Za-z_]\w*\b)"
)


_HASH_COMMENTS = {"", "python", "py", "bash", "sh", "shell", "powershell", "ps1", "ruby", "yaml", "yml", "toml"}


def code_text(text: str) -> str:
    return esc(text).replace(" ", "&nbsp;")


def highlight(line: str, language: str = "") -> str:
    out, pos = [], 0
    for m in _TOKEN.finditer(line):
        out.append(code_text(line[pos:m.start()]))
        kind = m.lastgroup
        token = code_text(m.group())
        if kind == "word" and m.group() not in KEYWORDS:
            out.append(token)
        elif kind == "comment" and m.group().startswith("#") and language not in _HASH_COMMENTS:
            out.append(token)
        else:
            color = C["kw"] if kind == "word" else C[kind]
            out.append(f'<span style="color:{color};">{token}</span>')
        pos = m.end()
    out.append(code_text(line[pos:]))
    return "".join(out)

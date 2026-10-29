from PyQt5.QtCore import Qt, QUrl, QPoint
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QWidget, QFrame, QPushButton, QVBoxLayout, QApplication
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile

from core.ui import theme
from core.ui.theme import C
from core.ui.messages import hbox, label
from core.log import get_logger
log = get_logger(__name__)

ALLOWED_SCHEMES = {"data", "about", "blob", "qrc"}


class OfflineInterceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        url = info.requestUrl()
        if url.scheme() not in ALLOWED_SCHEMES:
            log.info(f"[Visual] Blocked request to {url.toString()[:120]}")
            info.block(True)


class VisualWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MARA · visual")
        self.setWindowIcon(theme.app_icon())
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(860, 620)
        self._drag: QPoint | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        root = QFrame()
        root.setObjectName("VisualRoot")
        outer.addWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)

        header = QFrame()
        header.setObjectName("Header")
        header.setFixedHeight(46)
        self.title = label("visual", "VisualTitle", theme.mono(12))
        close = QPushButton()
        close.setObjectName("IconButton")
        close.setFixedSize(30, 30)
        close.setIcon(theme.icon("close", C["tertiary"], 15))
        close.setToolTip("Close visual")
        close.clicked.connect(self.hide)
        header.setLayout(hbox(label("MARA", "Wordmark", theme.mono(12, 600, spacing_em=0.24)), 14, self.title, None,
                              close, margins=(18, 0, 10, 0)))
        lay.addWidget(header)
        self.header = header

        self.interceptor = OfflineInterceptor(self)
        QWebEngineProfile.defaultProfile().setUrlRequestInterceptor(self.interceptor)
        self.view = QWebEngineView()
        self.view.page().setBackgroundColor(QColor(C["ground"]))
        lay.addWidget(self.view, 1)

    def show_html(self, html: str, title: str = ""):
        self.title.setText((title or "visual").lower())
        self.view.setHtml(html, QUrl("about:blank"))
        if not self.isVisible():
            screen = QApplication.primaryScreen().availableGeometry()
            self.move(screen.center() - self.rect().center())
        self.show()
        self.raise_()
        self.activateWindow()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.pos().y() <= self.header.height():
            self._drag = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag)

    def mouseReleaseEvent(self, event):
        self._drag = None

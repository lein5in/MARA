import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWebEngineWidgets import QWebEngineView  # noqa: F401
from PyQt5.QtWidgets import QApplication

from core import events as ev
from core.app_registry import get_registry
from core.config import START_HIDDEN
from core.log import get_logger

log = get_logger(__name__)
startup_log = get_logger("startup")


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    from core.ui import theme
    from core.ui.window import MainWindow
    from core.ui.visual import VisualWindow
    from core.ui.worker import MARAWorker
    from core.orb import MARAOrb
    from core import listener, shutdown

    theme.load_fonts()
    app.setStyleSheet(theme.build_qss())
    app.setWindowIcon(theme.app_icon())

    startup_log.info("MARA starting...")
    startup_log.info("Scanning applications...")
    startup_log.info(f"{len(get_registry())} applications indexed")

    window = MainWindow()
    visual = VisualWindow()
    orb = MARAOrb()
    worker = MARAWorker(listener=listener)
    listener.start()

    def on_event(event):
        window.on_event(event)
        if isinstance(event, ev.StateChanged):
            orb.set_state(event.state.value)
        elif isinstance(event, ev.Visual):
            visual.show_html(event.html, event.title)
        elif isinstance(event, ev.QuitRequested):
            app.quit()

    worker.sig_event.connect(on_event)
    window.send_text.connect(worker.submit)
    window.confirm.connect(worker.confirm)
    window.new_conversation.connect(worker.new_conversation)
    window.silent_toggled.connect(worker.set_silent)
    window.vision_toggled.connect(worker.set_vision)
    window.quit_requested.connect(app.quit)

    def on_quit():
        window.save_geometry()
        worker.stop()
        worker.wait(3000)
        shutdown.run()

    app.aboutToQuit.connect(on_quit)
    worker.start()
    if not START_HIDDEN:
        window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

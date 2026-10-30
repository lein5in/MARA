import os
import sys
import threading

from PyQt5.QtCore import Qt
from PyQt5.QtWebEngineWidgets import QWebEngineView  # noqa: F401
from PyQt5.QtWidgets import QApplication

from core import events as ev
from core.app_registry import get_registry
from core.config import START_HIDDEN
from core.log import get_logger

log = get_logger(__name__)
startup_log = get_logger("startup")


def _log_unhandled(exc_type, exc, tb):
    log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))


def main():
    sys.excepthook = _log_unhandled
    threading.excepthook = lambda args: _log_unhandled(args.exc_type, args.exc_value, args.exc_traceback)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    from core.ui import theme
    from core.ui.window import MainWindow
    from core.ui.visual import VisualWindow
    from core.ui.worker import MARAWorker
    from core.orb import MARAOrb
    from core import listener, shutdown, voice
    from core.tools import vision_tools, browser_tools
    from core.ui.secret import ask_password

    theme.apply(app)

    startup_log.info("MARA starting...")
    startup_log.info("Scanning applications...")
    startup_log.info(f"{len(get_registry())} applications indexed")

    window = MainWindow()
    visual = VisualWindow()
    orb = MARAOrb()
    orb.set_output_level_source(voice.output_level)
    worker = MARAWorker(listener=listener)
    listener.start()

    def on_event(event):
        window.on_event(event)
        if isinstance(event, ev.StateChanged):
            orb.set_state(event.state.value)
        elif isinstance(event, ev.MicLevel):
            orb.set_level(event.level)
        elif isinstance(event, ev.Visual):
            visual.show_html(event.html, event.title)
        elif isinstance(event, ev.QuitRequested):
            app.quit()

    hidden_for_capture = []

    def on_capture(hide: bool):
        if hide:
            hidden_for_capture[:] = [w for w in (window, orb, visual) if w.isVisible()]
            for w in hidden_for_capture:
                w.hide()
        else:
            for w in hidden_for_capture:
                w.show()
            hidden_for_capture.clear()
        app.processEvents()

    worker.sig_event.connect(on_event)
    worker.sig_capture.connect(on_capture, Qt.BlockingQueuedConnection)
    vision_tools.set_capture_hook(worker.sig_capture.emit)

    def on_secret(site: str, email: str):
        worker.secret_result = ask_password(site, email, window if window.isVisible() else None)

    worker.sig_secret.connect(on_secret, Qt.BlockingQueuedConnection)
    browser_tools.set_secret_prompt(worker.ask_secret)
    window.send_text.connect(worker.submit)
    window.confirm.connect(worker.confirm)
    window.new_conversation.connect(worker.new_conversation)
    window.silent_toggled.connect(worker.set_silent)
    window.vision_toggled.connect(worker.set_vision)
    window.quit_requested.connect(app.quit)

    def on_quit():
        window.save_geometry()
        worker.stop()
        if not worker.wait(3000):
            log.warning("Worker still busy at quit, forcing exit.")
            shutdown.run()
            os._exit(0)
        shutdown.run()

    app.aboutToQuit.connect(on_quit)
    worker.start()
    if not START_HIDDEN:
        window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

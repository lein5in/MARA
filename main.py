import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from core.ui import MARAWindow, MARAWorker
from core.orb import MARAOrb
from core.app_registry import get_registry
from core import events as ev
from core.log import get_logger

log = get_logger(__name__)
startup_log = get_logger("startup")

def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    startup_log.info("MARA starting...")
    startup_log.info("Scanning applications...")
    registry = get_registry()
    startup_log.info(f"{len(registry)} applications indexed")

    worker = MARAWorker()
    window = MARAWindow(worker.submit)
    window.hide()
    orb = MARAOrb()

    def on_event(event):
        window.on_event(event)
        if isinstance(event, ev.StateChanged):
            orb.set_state(event.state.value.upper())
        elif isinstance(event, ev.QuitRequested):
            app.quit()

    worker.sig_event.connect(on_event)
    worker.start()

    def on_quit():
        worker.stop()
        worker.wait(3000)

    app.aboutToQuit.connect(on_quit)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()

import sys
import queue
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from core.ui import MARAWindow, MARAWorker
from core.orb import MARAOrb
from core.app_registry import get_registry

def main():
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_EnableHighDpiScaling)
    app.setQuitOnLastWindowClosed(False)

    print("MARA initialisée.")
    print("Scan des applications...")
    get_registry()

    text_queue = queue.Queue()

    # ── Interface texte ───────────────────────────────────────────────────────
    window = MARAWindow(text_queue)
    window.hide()

    # ── Orbe neural ───────────────────────────────────────────────────────────
    orb = MARAOrb()
    # Pas de show() — l'orbe est invisible jusqu'au premier état actif

    # ── Worker ────────────────────────────────────────────────────────────────
    worker = MARAWorker(text_queue)

    # Signaux → interface texte
    worker.sig_status.connect(window.on_status)
    worker.sig_stream_start.connect(window.on_mara_stream_start)
    worker.sig_chunk.connect(window.on_mara_chunk)
    worker.sig_done.connect(window.on_mara_done)
    worker.sig_user_msg.connect(window.on_user_message)
    worker.sig_password_mode.connect(window.on_password_mode)
    worker.sig_show.connect(window.show)
    worker.sig_hide.connect(window.hide)
    worker.sig_visual.connect(window.on_visual)

    # Signaux → orbe
    worker.sig_status.connect(orb.set_state)

    worker.start()

    def on_quit():
        worker.stop()
        worker.wait(3000)

    app.aboutToQuit.connect(on_quit)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
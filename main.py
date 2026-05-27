import sys
import queue
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from core.ui import MARAWindow, MARAWorker
from core.app_registry import get_registry

def main():
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_EnableHighDpiScaling)
    app.setQuitOnLastWindowClosed(False)

    print("MARA initialisée.")
    print("Scan des applications...")
    get_registry()

    text_queue = queue.Queue()

    window = MARAWindow(text_queue)
    window.hide()  # Interface cachée au démarrage — "show interface" pour l'ouvrir

    worker = MARAWorker(text_queue)
    worker.sig_status.connect(window.on_status)
    worker.sig_stream_start.connect(window.on_mara_stream_start)
    worker.sig_chunk.connect(window.on_mara_chunk)
    worker.sig_done.connect(window.on_mara_done)
    worker.sig_user_msg.connect(window.on_user_message)
    worker.sig_password_mode.connect(window.on_password_mode)
    worker.sig_show.connect(window.show)
    worker.sig_hide.connect(window.hide)  # ui_hide intent
    worker.start()

    def on_quit():
        worker.stop()
        worker.wait(3000)

    app.aboutToQuit.connect(on_quit)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
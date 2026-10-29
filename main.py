import sys
import queue
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from core.ui import MARAWindow, MARAWorker
from core.orb import MARAOrb
from core.app_registry import get_registry
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

    text_queue = queue.Queue()

  
    window = MARAWindow(text_queue)
    window.hide()

   
    orb = MARAOrb()
   

   
    worker = MARAWorker(text_queue)

   
    worker.sig_status.connect(window.on_status)
    worker.sig_stream_start.connect(window.on_mara_stream_start)
    worker.sig_chunk.connect(window.on_mara_chunk)
    worker.sig_done.connect(window.on_mara_done)
    worker.sig_user_msg.connect(window.on_user_message)
    worker.sig_password_mode.connect(window.on_password_mode)
    worker.sig_show.connect(window.show)
    worker.sig_hide.connect(window.hide)
    worker.sig_visual.connect(window.on_visual)

    
    worker.sig_status.connect(orb.set_state)

    worker.start()

    def on_quit():
        worker.stop()
        worker.wait(3000)

    app.aboutToQuit.connect(on_quit)
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
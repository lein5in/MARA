from PyQt5.QtCore import QThread, pyqtSignal

from core import system
from core.events import ModeChanged
from core.session import Session


class MARAWorker(QThread):
    sig_event = pyqtSignal(object)

    def __init__(self, session: Session | None = None, listener=None):
        super().__init__()
        self.listener = listener
        if listener is not None:
            listener.set_event_hook(self.sig_event.emit)
        self.session = session or Session(self.sig_event.emit, listen_fn=listener.listen if listener else None)

    def submit(self, text: str):
        self.session.submit(text, "typed")

    def confirm(self, cid: str, accepted: bool):
        self.session.resolve_confirmation(accepted, cid)

    def new_conversation(self):
        self.session.new_conversation()

    def set_silent(self, on: bool):
        system.set_silent(on)
        self.sig_event.emit(ModeChanged(system.is_silent(), system.is_vision()))

    def set_vision(self, on: bool):
        system.set_vision(on)
        self.sig_event.emit(ModeChanged(system.is_silent(), system.is_vision()))

    def run(self):
        self.session.run()

    def stop(self):
        self.session.stop()

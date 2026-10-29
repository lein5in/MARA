from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QPushButton

from core.ui import theme
from core.ui.messages import hbox, label


class SecretDialog(QDialog):
    def __init__(self, site: str, email: str, parent=None):
        super().__init__(parent)
        self.setObjectName("SecretDialog")
        self.setWindowTitle("MARA · password")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setModal(True)
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(12)
        lay.addWidget(label(f"Password for {site}", "ConfirmTitle", theme.body(14, 600)))
        hint = label(f"{email}\nTyped here only: it goes straight to the encrypted vault and is never sent to the model.",
                     "ConfirmDesc", theme.body(12.5))
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.field = QLineEdit()
        self.field.setObjectName("SecretInput")
        self.field.setEchoMode(QLineEdit.Password)
        self.field.setFont(theme.mono(13.5))
        self.field.setFixedHeight(36)
        lay.addWidget(self.field)
        cancel = QPushButton("cancel")
        cancel.setObjectName("GhostButton")
        save = QPushButton("save")
        save.setObjectName("SendButton")
        for b in (cancel, save):
            b.setFont(theme.mono(12.5, 600))
            b.setFixedHeight(34)
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        save.setDefault(True)
        lay.addLayout(hbox(None, cancel, 10, save))

    def password(self) -> str:
        return self.field.text()


def ask_password(site: str, email: str, parent=None) -> str | None:
    dialog = SecretDialog(site, email, parent)
    dialog.raise_()
    dialog.activateWindow()
    accepted = dialog.exec_() == QDialog.Accepted
    value = dialog.password() if accepted else None
    dialog.field.clear()
    dialog.deleteLater()
    return value or None

import sys
import types

import pytest

pytest.importorskip("PyQt5.QtWebEngineWidgets")
from PyQt5.QtWebEngineWidgets import QWebEngineView  # noqa: E402,F401
from PyQt5.QtCore import Qt, QSettings  # noqa: E402
from PyQt5.QtGui import QGuiApplication  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from core import events as ev, system  # noqa: E402
from core.events import State  # noqa: E402


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication(sys.argv)
    from core.ui import theme
    theme.apply(instance)
    return instance


@pytest.fixture
def win(app, tmp_path):
    from core.ui.window import MainWindow
    w = MainWindow(QSettings(str(tmp_path / "ui.ini"), QSettings.IniFormat))
    w.show()
    app.processEvents()
    yield w
    w.hide()
    w.deleteLater()


def signals(sig):
    got = []
    sig.connect(lambda *a: got.append(a))
    return got


def test_header_buttons(win, app):
    win.on_event(ev.TurnStarted("hello", "typed"))
    win.on_event(ev.TextDelta("Hi."))
    win.on_event(ev.Done())
    reset = signals(win.new_conversation)
    win.header.buttons["new"].click()
    app.processEvents()
    assert reset == [()]
    assert win.thread.count() == 1
    before = win.geometry()
    win.header.buttons["expand"].click()
    assert win.geometry() != before
    win.header.buttons["expand"].click()
    assert win.geometry() == before
    win.header.buttons["hide"].click()
    assert not win.isVisible()


def test_tray_menu_actions(win):
    actions = {a.text(): a for a in win.tray_menu.actions() if a.text()}
    assert set(actions) == {"Show MARA", "New conversation", "Quit MARA"}
    win.hide()
    actions["Show MARA"].trigger()
    assert win.isVisible()
    quit_sig = signals(win.quit_requested)
    actions["Quit MARA"].trigger()
    assert quit_sig == [()]


def test_composer_enter_sends_shift_enter_newlines(win):
    sent = signals(win.send_text)
    box = win.composer.input
    assert not win.composer.button.isEnabled()
    QTest.keyClicks(box, "line one")
    QTest.keyClick(box, Qt.Key_Return, Qt.ShiftModifier)
    QTest.keyClicks(box, "line two")
    assert win.composer.button.isEnabled()
    QTest.keyClick(box, Qt.Key_Return)
    assert sent == [("line one\nline two",)]
    assert box.toPlainText() == ""
    QTest.keyClicks(box, "again")
    win.composer.button.click()
    assert sent[-1] == ("again",)


def test_toggles_and_mode_model(win):
    silent = signals(win.silent_toggled)
    vision = signals(win.vision_toggled)
    win.footer.silent.click()
    win.footer.vision.click()
    assert silent == [(True,)] and vision == [(True,)]
    win.on_event(ev.ModeChanged(silent=False, vision=True))
    assert not win.footer.silent.isChecked() and win.footer.vision.isChecked()
    assert win.header.status.text() == "ready · vision on"
    assert win.footer.silent.text().startswith("[ ]") and win.footer.vision.text().startswith("[x]")


def test_status_texts(win):
    expected = {
        State.IDLE: "ready · sonnet 5", State.LISTENING: "listening", State.THINKING: "thinking",
        State.SPEAKING: "speaking", State.WAITING_CONFIRMATION: "waiting for confirmation", State.PAUSED: "paused",
    }
    for state, text in expected.items():
        win.on_event(ev.StateChanged(state))
        assert win.header.status.text() == text


def test_listening_state_ui(win):
    win.on_event(ev.StateChanged(State.LISTENING))
    assert win.listen_bar.isVisible()
    assert win.composer_area.stack.currentWidget() is win.composer_area.strip
    win.on_event(ev.UserTranscript("What time", final=False))
    win.on_event(ev.MicLevel(0.5, 3.2))
    assert win.composer_area.strip.rec.text() == "rec 00:03"
    assert win.live is not None and win.live.live
    win.on_event(ev.StateChanged(State.THINKING))
    win.on_event(ev.TurnStarted("What time is it in Tokyo?", "voice"))
    assert win.live is None
    assert not win.listen_bar.isVisible()


def test_empty_transcript_removes_live_block(win):
    win.on_event(ev.UserTranscript("", final=False))
    assert win.live is not None
    win.on_event(ev.UserTranscript("", final=True))
    assert win.live is None


def test_streaming_appends_without_rebuilding(win):
    win.on_event(ev.TurnStarted("hi", "typed"))
    win.on_event(ev.TextDelta("Hello"))
    label = win.block.reply._widgets[0]
    win.on_event(ev.TextDelta(" there, `code` and **bold**."))
    assert win.block.reply._widgets[0] is label
    assert "font-weight:600" in label.text() and "**" not in label.text() and "`" not in label.text()
    win.on_event(ev.TextDelta("\n```python\nprint(1)\n```\nAfter."))
    kinds = win.block.reply._kinds
    assert kinds == ["text", "code", "text"]
    assert win.block.reply._widgets[0] is label


def test_receipts_and_confirmation_card(win):
    answers = signals(win.confirm)
    win.on_event(ev.TurnStarted("close spotify", "voice"))
    win.on_event(ev.ToolStarted("t1", "open_app", {"name": "x"}, "x"))
    win.on_event(ev.ToolFinished("t1", "open_app", True, 0.8, "ok"))
    row = win.block.receipts.rows["t1"]
    assert row.time.text() == "0.8s"
    win.on_event(ev.ToolStarted("t2", "kill_process", {"process": "a.exe"}, "a.exe"))
    win.on_event(ev.ConfirmationRequested("t2", "Close application", "desc", "kill_process", {"process": "a.exe"}))
    assert win.composer.locked and not win.composer.button.isEnabled()
    card = win.cards["t2"]
    assert card.confirm_btn.text() == "close"
    card.confirm_btn.click()
    assert answers == [("t2", True)]
    win.on_event(ev.ConfirmationResolved("t2", True))
    assert not win.composer.locked and not card.confirm_btn.isEnabled()


def test_cancel_button(win):
    answers = signals(win.confirm)
    win.on_event(ev.TurnStarted("x", "typed"))
    win.on_event(ev.ConfirmationRequested("c1", "Erase all memory", "desc", "reset_memory", {}))
    win.cards["c1"].cancel_btn.click()
    assert answers == [("c1", False)]


def test_code_copy_button(win, app):
    win.on_event(ev.TurnStarted("fix", "typed"))
    win.on_event(ev.TextDelta("Fix:\n```python fix\n a = 1\n-b = 2\n+b = 3\n```"))
    win.on_event(ev.Done())
    blocks = [w for w in (win.thread.itemAt(i).widget() for i in range(win.thread.count())) if hasattr(w, "reply")]
    code = blocks[-1].reply.code_blocks()[0]
    assert code.lang.text() == "python · suggested fix"
    code.copy_btn.click()
    assert QGuiApplication.clipboard().text() == "a = 1\nb = 3"
    assert code.copy_btn.text().strip() == "copied"


def test_no_json_or_sentinels_shown(win):
    win.on_event(ev.TurnStarted("x", "typed"))
    win.on_event(ev.TextDelta("Done."))
    win.on_event(ev.Error("Cannot reach Claude."))
    win.on_event(ev.Done())
    blocks = [w for w in (win.thread.itemAt(i).widget() for i in range(win.thread.count())) if hasattr(w, "reply")]
    assert "Cannot reach Claude." in blocks[-1].error.text()


def test_worker_mode_and_controls(app, monkeypatch):
    from core.ui.worker import MARAWorker
    calls = []
    session = types.SimpleNamespace(
        submit=lambda t, s: calls.append(("submit", t, s)),
        resolve_confirmation=lambda a, c: calls.append(("confirm", a, c)),
        new_conversation=lambda: calls.append(("new",)),
        run=lambda: None, stop=lambda: None,
    )
    worker = MARAWorker(session=session)
    events = signals(worker.sig_event)
    worker.submit("hello")
    worker.confirm("id1", True)
    worker.new_conversation()
    worker.set_silent(True)
    worker.set_vision(True)
    assert system.is_silent() and system.is_vision()
    assert events[-1] == (ev.ModeChanged(True, True),)
    system.set_silent(False)
    system.set_vision(False)
    assert calls == [("submit", "hello", "typed"), ("confirm", True, "id1"), ("new",)]


def test_shutdown_closes_browser(monkeypatch):
    from core import shutdown
    closed = []
    fake = types.SimpleNamespace(browser=types.SimpleNamespace(is_open=True, close=lambda: closed.append(True)))
    monkeypatch.setitem(sys.modules, "core.browser", fake)
    shutdown._done.clear()
    shutdown.run()
    shutdown.run()
    assert closed == [True]


def test_visual_interceptor_blocks_network(app):
    from PyQt5.QtCore import QUrl
    from core.ui.visual import OfflineInterceptor

    class Info:
        def __init__(self, url):
            self.url, self.blocked = QUrl(url), False

        def requestUrl(self):
            return self.url

        def block(self, flag):
            self.blocked = flag

    interceptor = OfflineInterceptor()
    for url, blocked in (("https://cdn.example.com/x.js", True), ("http://a.b", True),
                         ("file:///C:/secret.txt", True), ("data:image/png;base64,AA", False),
                         ("about:blank", False)):
        info = Info(url)
        interceptor.interceptRequest(info)
        assert info.blocked is blocked, url

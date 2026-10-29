import threading
import time
from datetime import datetime, timedelta

from core import system, voice
from core.brain import Agent
from core.events import ConfirmationRequested, StateChanged, State, Error, UserTranscript, ToolStarted
from core.session import Session
from core.tools import build_registry
from tests.fakes import FakeAnthropic, FakeMemory, reply, tool_call


class Speech:
    def __init__(self, log, failed=None):
        self.log, self.failed = log, failed

    def feed(self, text):
        self.log.append(("feed", text))

    def end(self, timeout=None):
        self.log.append(("end",))

    def cancel(self):
        self.log.append(("cancel",))


def make(*script, speech_failed=None, listen_fn=None):
    events, log = [], []
    agent = Agent(client=FakeAnthropic(script), registry=build_registry(), memory=FakeMemory(), background=False)
    session = Session(events.append, agent=agent, speech_factory=lambda: Speech(log, speech_failed),
                      say_fn=lambda t: None, listen_fn=listen_fn)
    return session, events, log


def _start_pending(session, monkeypatch):
    import psutil
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [])
    session.submit("close x")
    worker = threading.Thread(target=session.step)
    worker.start()
    for _ in range(200):
        if session.broker.pending_id():
            break
        time.sleep(0.01)
    return worker


def test_f13_during_confirmation_keeps_the_question_open(monkeypatch):
    session, events, log = make(tool_call("kill_process", {"process": "x.exe"}), reply("Done."))
    worker = _start_pending(session, monkeypatch)
    assert session.barge_in()
    assert session.broker.pending_id() is not None
    assert session.submit("yes", "voice")
    worker.join(2)
    assert UserTranscript("", final=True) in events
    assert any(type(e).__name__ == "ConfirmationResolved" and e.accepted for e in events)
    assert not session.agent._cancel.is_set()


def test_unclear_voice_answer_keeps_waiting_state(monkeypatch):
    session, events, _ = make(tool_call("kill_process", {"process": "x.exe"}), reply("Ok."))
    worker = _start_pending(session, monkeypatch)
    assert not session.submit("hmm", "voice")
    assert events[-1] == StateChanged(State.WAITING_CONFIRMATION)
    session.submit("no", "voice")
    worker.join(2)


def test_new_conversation_cancels_pending_confirmation(monkeypatch):
    session, events, _ = make(tool_call("kill_process", {"process": "x.exe"}), reply("Ok."))
    worker = _start_pending(session, monkeypatch)
    session.new_conversation()
    worker.join(2)
    assert not worker.is_alive() and session.broker.pending_id() is None


def test_empty_recording_while_paused_keeps_paused():
    calls = iter(["", None])
    session, events, _ = make()
    system.set_pause(datetime.now().astimezone() + timedelta(hours=1), session.memory)

    def listen():
        value = next(calls)
        if value is None:
            session.running = False
            return ""
        return value
    session.listen_fn = listen
    session._voice_loop()
    assert StateChanged(State.PAUSED) in events
    system.cancel_pause(session.memory)


def test_listener_crash_reports_and_unsticks_ui():
    session, events, _ = make()
    state = {"n": 0}

    def listen():
        state["n"] += 1
        if state["n"] == 1:
            raise OSError("no microphone")
        session.running = False
        return ""
    session.listen_fn = listen
    session._voice_loop()
    assert any(isinstance(e, Error) and "Voice input failed" in e.message for e in events)
    assert UserTranscript("", final=True) in events
    assert StateChanged(State.IDLE) in events


def test_tool_start_switches_status_to_thinking(monkeypatch):
    monkeypatch.setattr(system, "set_volume", lambda level: level)
    session, events, _ = make(tool_call("set_volume", {"level": 10}, "Lowering it."), reply("Done."))
    session.submit("volume 10")
    session.step()
    i = next(i for i, e in enumerate(events) if isinstance(e, ToolStarted))
    assert events[i - 1] == StateChanged(State.THINKING)


def test_speech_failure_is_reported():
    session, events, _ = make(reply("Hello."), speech_failed="Voice output failed (ConnectionError).")
    session.submit("hi")
    session.step()
    assert any(isinstance(e, Error) and "Voice output failed" in e.message for e in events)


def test_audio_out_pending_counter(monkeypatch):
    written = []

    class Stream:
        def start(self):
            pass

        def write(self, data):
            time.sleep(0.01)
            written.append(len(data))

        def stop(self):
            pass

        def close(self):
            pass

        def abort(self):
            pass
    monkeypatch.setattr(voice.sd, "OutputStream", lambda **kw: Stream())
    out = voice.AudioOut()
    out.write(b"\x00\x01" * voice.WRITE_BYTES)
    assert system.is_speaking()
    assert out.wait_idle(5)
    assert len(written) == 2 and sum(written) * 2 == voice.WRITE_BYTES * 2
    assert not system.is_speaking()
    out.close()


def test_secret_inputs_reach_the_tool_but_not_history():
    reg = build_registry()
    seen = {}

    @reg.tool("needs_token", "test", {"token": {"type": "string"}}, ["token"])
    def needs_token(ctx, token):
        seen["token"] = token
        return "ok"

    agent = Agent(client=FakeAnthropic([tool_call("needs_token", {"token": "abc123"}), reply("ok")]),
                  registry=reg, memory=FakeMemory(), background=False)
    events = []
    agent.emit = events.append
    agent.run_turn("go")
    assert seen["token"] == "abc123"
    assert "abc123" not in str(agent.history) and "abc123" not in str(events)
    assert any(isinstance(e, ConfirmationRequested) for e in events) is False

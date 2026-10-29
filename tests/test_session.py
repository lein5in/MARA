import threading
import time
from datetime import datetime, timedelta

import pytest

from core import system
from core.brain import Agent
from core.events import QuitRequested, StateChanged, State, TurnStarted, ConfirmationRequested, Error
from core.session import Session
from core.text import parse_yes_no
from core.tools import build_registry
from tests.fakes import FakeAnthropic, FakeMemory, reply, tool_call


class FakeSpeech:
    def __init__(self, log):
        self.log = log

    def feed(self, text):
        self.log.append(("feed", text))

    def end(self, timeout=None):
        self.log.append(("end",))

    def cancel(self):
        self.log.append(("cancel",))


def make_session(*script):
    events, speech, said = [], [], []
    agent = Agent(client=FakeAnthropic(script), registry=build_registry(), memory=FakeMemory(), background=False)
    session = Session(events.append, agent=agent, speech_factory=lambda: FakeSpeech(speech), say_fn=said.append)
    return session, events, speech, said


@pytest.mark.parametrize("text, expected", [
    ("yes", True), ("Oui vas-y", True), ("okay do it", True), ("نعم", True),
    ("no", False), ("cancel that", False), ("non merci", False), ("لا", False),
    ("I'm not going", False), ("google token", None), ("going", None), ("hmm", None),
])
def test_parse_yes_no_whole_words(text, expected):
    assert parse_yes_no(text) is expected


def test_turn_streams_to_speech_and_ends():
    session, events, speech, _ = make_session(reply("Hello", " sir."))
    session.submit("hi")
    session.step()
    assert speech == [("feed", "Hello"), ("feed", " sir."), ("end",)]
    assert isinstance(events[0], TurnStarted) and events[0].source == "typed"
    assert StateChanged(State.SPEAKING) in events
    assert events[-1] == StateChanged(State.IDLE)


def test_quit_waits_for_goodbye():
    session, events, speech, _ = make_session(tool_call("quit_mara"), reply("Goodbye."))
    session.submit("shut down")
    session.step()
    assert not session.running
    assert isinstance(events[-1], QuitRequested)
    assert speech[-1] == ("end",)
    assert [e for e in events if isinstance(e, QuitRequested)] == [events[-1]]


def test_confirmation_by_voice_or_text(monkeypatch):
    import psutil
    monkeypatch.setattr(psutil, "process_iter", lambda attrs: [])
    session, events, _, _ = make_session(tool_call("kill_process", {"process": "x.exe"}), reply("Cancelled."))
    session.submit("close x")
    worker = threading.Thread(target=session.step)
    worker.start()
    for _ in range(100):
        if session.broker.pending_id():
            break
        time.sleep(0.01)
    assert any(isinstance(e, ConfirmationRequested) for e in events)
    assert not session.submit("hmm maybe")
    assert any(isinstance(e, Error) for e in events)
    assert session.submit("no, cancel", "voice")
    worker.join(2)
    assert not worker.is_alive()
    assert session.inputs.empty()


def test_pause_wake_word():
    session, events, _, said = make_session()
    system.set_pause(datetime.now().astimezone() + timedelta(hours=1), session.memory)
    session.submit("hello there")
    session.step()
    assert said and "paused" in said[-1].lower()
    assert system.is_paused(session.memory)
    session.submit("Mara, wake up")
    session.step()
    assert not system.is_paused(session.memory)
    assert events[-1] == StateChanged(State.IDLE)


def test_wake_word_is_whole_word():
    session, _, _, said = make_session()
    system.set_pause(datetime.now().astimezone() + timedelta(hours=1), session.memory)
    session.submit("tamarama beach")
    session.step()
    assert system.is_paused(session.memory)
    system.cancel_pause(session.memory)


def test_crashing_turn_does_not_kill_loop(monkeypatch):
    session, events, _, _ = make_session(reply("ok"))
    monkeypatch.setattr(session.agent, "run_turn", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    session.submit("hi")
    session.step()
    assert any(isinstance(e, Error) for e in events)
    assert session.running

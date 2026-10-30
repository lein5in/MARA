from PIL import Image

from core import system
from core.brain import Agent, validate_history
from core.events import Done, Error, StateChanged, State, TextDelta, TurnStarted
from core.session import Session, TURN_FAILED, localized
from core.tools import build_registry
from tests.fakes import FakeAnthropic, FakeMemory, hang, reply, tool_call

CODE_REPLY = "Line 3 divides by zero.\n```python fix\n-    return a / b\n+    return a / b if b else 0\n```"


def make_session(*script, watchdog=None):
    events, said = [], []
    agent = Agent(client=FakeAnthropic(script), registry=build_registry(), memory=FakeMemory(), background=False)
    if watchdog is not None:
        agent.watchdog_timeout = watchdog
    session = Session(events.append, agent=agent, speech_factory=lambda: _NoSpeech(), say_fn=said.append)
    return session, agent, events, said


class _NoSpeech:
    def feed(self, text):
        pass

    def end(self, timeout=None):
        pass

    def cancel(self):
        pass


def _screen(monkeypatch):
    monkeypatch.setattr(system, "active_monitor_rect", lambda: ((0, 0, 800, 600), True))
    monkeypatch.setattr(system, "grab_screen", lambda bbox: Image.new("RGB", (800, 600), (20, 30, 40)))


def _turn(session, events, text):
    start = len(events)
    session.submit(text)
    session.step()
    return events[start:]


def test_follow_up_after_vision_turn_cut_in_tool_call_still_answers(monkeypatch):
    _screen(monkeypatch)
    session, agent, events, said = make_session(
        tool_call("look_at_screen"), reply(CODE_REPLY),
        tool_call("show_visual", {"html": "<html><body>long expl"}, stop_reason="max_tokens"),
        reply("It still divides by zero on line 3."),
    )
    _turn(session, events, "Review the code on my screen")
    second = _turn(session, events, "Check again what is wrong")
    assert "".join(e.text for e in second if isinstance(e, TextDelta)) == "It still divides by zero on line 3."
    assert agent.client.messages.calls[-1].get("tool_choice") == {"type": "none"}
    assert second[-1] == StateChanged(State.IDLE)
    assert validate_history(agent.history) == []


def test_empty_reply_shows_error_and_speaks(monkeypatch):
    session, agent, events, said = make_session(reply())
    out = _turn(session, events, "hello?")
    assert any(isinstance(e, Error) for e in out)
    assert said == [localized(TURN_FAILED)]
    assert out[-1] == StateChanged(State.IDLE)


def test_cut_off_text_reply_reports_error():
    session, agent, events, said = make_session(reply("A very long answer", stop_reason="max_tokens"))
    out = _turn(session, events, "explain")
    assert any(isinstance(e, Error) and "cut off" in e.message for e in out)
    assert out[-1] == StateChanged(State.IDLE)


def test_watchdog_aborts_silent_stream():
    session, agent, events, said = make_session(hang(), reply("Back."), watchdog=0.3)
    out = _turn(session, events, "Check again")
    errors = [e for e in out if isinstance(e, Error)]
    assert len(errors) == 1 and "no response" in errors[0].message
    assert said == [localized(TURN_FAILED)]
    assert any(isinstance(e, Done) for e in out)
    assert out[-1] == StateChanged(State.IDLE)
    assert validate_history(agent.history) == []
    next_turn = _turn(session, events, "hi")
    assert isinstance(next_turn[0], TurnStarted)
    assert "".join(e.text for e in next_turn if isinstance(e, TextDelta)) == "Back."


def test_unexpected_exception_speaks_and_returns_idle():
    session, agent, events, said = make_session(tool_call("look_at_screen"))
    agent.registry.execute = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    out = _turn(session, events, "look")
    assert any(isinstance(e, Error) for e in out)
    assert said == [localized(TURN_FAILED)]
    assert out[-1] == StateChanged(State.IDLE)

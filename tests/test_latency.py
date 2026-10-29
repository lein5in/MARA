import numpy as np

from core import metrics
from core.brain import Agent, validate_history
from core.events import TextDelta
from core.session import Session
from core.tools import build_registry
from tests.fakes import FakeAnthropic, FakeMemory, reply


def test_metrics_recap_order():
    metrics.start("voice", at=10.0)
    metrics.mark("whisper_done", at=10.4)
    metrics.mark("first_token", at=11.0)
    metrics.mark("first_token", at=12.0)
    metrics.mark("first_audio", at=11.3)
    metrics.mark("done", at=13.0)
    recap = metrics.finish()
    assert recap == {"source": "voice", "released": 0.0, "whisper_done": 0.4, "first_token": 1.0,
                     "first_audio": 1.3, "done": 3.0}
    assert metrics.RECAPS[-1] == recap
    assert "first_token=+1.00s" in metrics.format_recap(recap)
    assert metrics.finish() is None


def test_session_records_typed_turn():
    agent = Agent(client=FakeAnthropic([reply("Hi.")]), registry=build_registry(), memory=FakeMemory(), background=False)
    session = Session(lambda e: None, agent=agent, speech_factory=lambda: _Speech([]), say_fn=lambda t: None)
    session.submit("hello")
    session.step()
    recap = metrics.RECAPS[-1]
    assert recap["source"] == "typed" and "first_token" in recap and "done" in recap


class _Speech:
    def __init__(self, log):
        self.log = log

    def feed(self, text):
        self.log.append(("feed", text))

    def end(self, timeout=None):
        self.log.append(("end",))

    def cancel(self):
        self.log.append(("cancel",))


def test_barge_in_cancels_speech_and_request():
    log = []
    script = [reply("This is a long answer", " that keeps", " going and going.")]
    agent = Agent(client=FakeAnthropic(script), registry=build_registry(), memory=FakeMemory(), background=False)
    session = Session(lambda e: None, agent=agent, speech_factory=lambda: _Speech(log), say_fn=lambda t: None)
    original = session._on_agent_event

    def on_event(event):
        original(event)
        if isinstance(event, TextDelta) and event.text.startswith("This"):
            assert session.barge_in()
    agent.emit = on_event
    session.submit("tell me a story")
    session.step()
    assert ("cancel",) in log
    assert ("feed", " going and going.") not in log
    assert validate_history(agent.history) == []
    assert "interrupted by the user" in agent.history[-1]["content"][0]["text"]


def test_barge_in_when_idle_does_nothing():
    agent = Agent(client=FakeAnthropic([]), registry=build_registry(), memory=FakeMemory(), background=False)
    session = Session(lambda e: None, agent=agent, speech_factory=lambda: _Speech([]), say_fn=lambda t: None)
    assert session.barge_in() is False


def test_prompt_cache_breakpoint_and_dynamic_tail():
    agent = Agent(client=FakeAnthropic([reply("ok")]), registry=build_registry(), memory=FakeMemory(), background=False)
    agent.run_turn("hi")
    system = agent.client.messages.calls[0]["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert "Current local time" not in system[0]["text"]
    assert "Current local time" in system[1]["text"] and "cache_control" not in system[1]


def test_no_language_detection_call():
    agent = Agent(client=FakeAnthropic([reply("ok")]), registry=build_registry(), memory=FakeMemory(), background=True)
    agent.run_turn("hi")
    assert all(c["system"] != "Detect the language" for c in agent.client.messages.create_calls)
    assert not any("language of the user" in str(c.get("system")) for c in agent.client.messages.create_calls)


def test_listener_gate_and_preroll():
    from core import listener
    assert not listener.should_transcribe(np.zeros(16000, dtype=np.int16))
    loud = (np.sin(np.arange(16000) / 5) * 8000).astype(np.int16)
    assert listener.should_transcribe(loud)
    assert not listener.should_transcribe(loud[:3000])

    class FakeStream:
        def __init__(self, cb):
            self.cb = cb
            self.closed = False

        def start(self):
            pass

        def stop(self):
            pass

        def close(self):
            self.closed = True

    holder = {}
    mic = listener.MicInput(preroll_seconds=0.1, stream_factory=lambda cb: holder.setdefault("s", FakeStream(cb)))
    stream = holder["s"]
    for i in range(10):
        stream.cb(np.full((512, 1), i, dtype=np.int16), 512, None, None)
    mic.begin()
    stream.cb(np.full((512, 1), 99, dtype=np.int16), 512, None, None)
    assert mic.next_chunk(0.1)[0] == 99
    audio = mic.end()
    assert audio[0] == 6 and audio[-1] == 99
    assert len(audio) == 5 * 512
    mic.close()
    assert stream.closed

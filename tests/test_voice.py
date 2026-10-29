import numpy as np

from core import voice, system


class _FakeTTS:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def convert(self, text, config):
        self.calls.append(text)
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


class _FakeClient:
    def __init__(self, data):
        self.tts = _FakeTTS(data)


def _patch(monkeypatch, data):
    played = []
    client = _FakeClient(data)
    monkeypatch.setattr(voice, "_client", client)
    monkeypatch.setattr(voice.sd, "play", lambda samples, samplerate: played.append(samples))
    monkeypatch.setattr(voice.sd, "wait", lambda: None)
    system.set_silent(False)
    return client, played


def test_speak_plays_bytes_output(monkeypatch):
    wav = b"RIFF" + b"\x00" * 40 + np.array([1, -2, 3], dtype=np.int16).tobytes() + b"\x07"
    client, played = _patch(monkeypatch, wav)
    voice.speak("Hello **there**.")
    assert client.tts.calls == ["Hello there."]
    assert len(played) == 1
    assert played[0].tolist() == [1, -2, 3]
    assert not system.is_speaking()


def test_speak_logs_errors(monkeypatch, caplog):
    _patch(monkeypatch, RuntimeError("network down"))
    with caplog.at_level("ERROR"):
        voice.speak("Hi.")
    assert "speak() failed" in caplog.text
    assert "network down" in caplog.text
    assert not system.is_speaking()


def test_speak_silent_does_nothing(monkeypatch):
    client, played = _patch(monkeypatch, b"")
    system.set_silent(True)
    try:
        voice.speak("Hi.")
    finally:
        system.set_silent(False)
    assert client.tts.calls == []
    assert played == []

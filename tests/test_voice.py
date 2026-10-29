import threading

import numpy as np
from fishaudio.types import FlushEvent

from core import voice, system


class FakeOut:
    def __init__(self):
        self.chunks = []
        self.cleared = 0

    def write(self, pcm):
        self.chunks.append(pcm)

    def clear(self):
        self.cleared += 1

    def wait_idle(self, timeout=None):
        return True


class FakeTTS:
    def __init__(self, data=b"", audio_chunks=None, gate=None):
        self.data = data
        self.calls = []
        self.events = []
        self.audio_chunks = audio_chunks or [b"\x01\x00\x02", b"\x00\x03\x00"]
        self.gate = gate

    def convert(self, text, config):
        self.calls.append(text)
        if isinstance(self.data, Exception):
            raise self.data
        return self.data

    def stream_websocket(self, text_stream, config):
        self.configs = getattr(self, "configs", []) + [config]
        for item in text_stream:
            self.events.append(item)
        if self.gate:
            self.gate.wait(2)
        for chunk in self.audio_chunks:
            yield chunk


class FakeClient:
    def __init__(self, **kw):
        self.tts = FakeTTS(**kw)


def _patch(monkeypatch, **kw):
    client = FakeClient(**kw)
    out = FakeOut()
    monkeypatch.setattr(voice, "_client", client)
    monkeypatch.setattr(voice, "_audio_out", out)
    system.set_silent(False)
    return client, out


def test_speak_plays_bytes_output(monkeypatch):
    wav = b"RIFF" + b"\x00" * 40 + np.array([1, -2, 3], dtype=np.int16).tobytes() + b"\x07"
    client, out = _patch(monkeypatch, data=wav)
    voice.speak("Hello **there**.")
    assert client.tts.calls == ["Hello there."]
    assert np.frombuffer(b"".join(out.chunks), dtype=np.int16).tolist() == [1, -2, 3]
    assert not system.is_speaking()


def test_speak_logs_errors(monkeypatch, caplog):
    _patch(monkeypatch, data=RuntimeError("network down"))
    with caplog.at_level("ERROR"):
        voice.speak("Hi.")
    assert "speak() failed" in caplog.text and "network down" in caplog.text
    assert not system.is_speaking()


def test_speak_silent_does_nothing(monkeypatch):
    client, out = _patch(monkeypatch)
    system.set_silent(True)
    try:
        voice.speak("Hi.")
    finally:
        system.set_silent(False)
    assert client.tts.calls == [] and out.chunks == []


def test_chunker_first_flush_at_punctuation():
    c = voice.TTSChunker(first_words=5)
    assert c.feed("Sure") == []
    assert c.feed(", I'll open ") == ["Sure,"]
    assert c.feed("it now. Then") == ["I'll open it now."]
    assert c.flush() == ["Then"]


def test_chunker_first_flush_after_five_words():
    c = voice.TTSChunker(first_words=5)
    assert c.feed("one two three four five") == []
    assert c.feed(" six seven") == ["one two three four five six"]
    assert c.feed(" eight. Next") == ["seven eight."]


def test_chunker_short_reply_flushes_at_end():
    c = voice.TTSChunker()
    assert c.feed("Done") == []
    assert c.flush() == ["Done"]


def test_streaming_speech_one_session_with_flushes(monkeypatch):
    client, out = _patch(monkeypatch)
    speech = voice.StreamingSpeech(out)
    for delta in ["Okay, ", "Spotify is ", "open. ", "Volume is ", "at forty."]:
        speech.feed(delta)
    speech.end(2)
    texts = [e for e in client.tts.events if isinstance(e, str)]
    flushes = [e for e in client.tts.events if isinstance(e, FlushEvent)]
    assert texts == ["Okay, ", "Spotify is open. ", "Volume is at forty."]
    assert len(flushes) == 3
    assert len(client.tts.configs) == 1 and client.tts.configs[0].format == "pcm"
    assert b"".join(out.chunks) == b"\x01\x00\x02\x00\x03\x00"
    assert all(len(c) % 2 == 0 for c in out.chunks)
    assert not system.is_speaking()


def test_streaming_speech_cancel(monkeypatch):
    gate = threading.Event()
    client, out = _patch(monkeypatch, gate=gate)
    speech = voice.StreamingSpeech(out)
    speech.feed("This is a long answer, ")
    speech.cancel()
    gate.set()
    speech.end(2)
    assert out.cleared == 1
    assert out.chunks == []
    assert not system.is_speaking()


def test_sentence_fallback(monkeypatch):
    wav_chunks = [b"RIFF" + b"\x00" * 40, b"\x05\x00\x06\x00"]
    client, out = _patch(monkeypatch, audio_chunks=wav_chunks)
    speech = voice.SentenceSpeech(out)
    speech.feed("First one. Second")
    speech.feed(" one.")
    speech.end(2)
    assert [e for e in client.tts.events] == ["First one.", "Second one."]
    assert b"".join(out.chunks) == b"\x05\x00\x06\x00" * 2


def test_make_speech_respects_flags(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr(voice, "STREAMING_TTS", False)
    s = voice.make_speech()
    assert isinstance(s, voice.SentenceSpeech)
    s.end(1)
    monkeypatch.setattr(voice, "STREAMING_TTS", True)
    s = voice.make_speech()
    assert isinstance(s, voice.StreamingSpeech)
    s.end(1)
    system.set_silent(True)
    assert isinstance(voice.make_speech(), voice.SilentSpeech)
    system.set_silent(False)

import re
import threading
import queue
import numpy as np
import sounddevice as sd
from fishaudio import FishAudio
from fishaudio.types import TTSConfig, FlushEvent
from core import system, metrics
from core.text import clean_text, pcm16_from_wav, SentenceBuffer, SpokenFilter
from core.config import (
    FISH_API_KEY, VOICE_ID, TTS_SAMPLE_RATE as SAMPLE_RATE, TTS_CHANNELS as CHANNELS, MIN_WORDS_SOFT,
    STREAMING_TTS, PERSISTENT_AUDIO_OUT, TTS_FIRST_CHUNK_WORDS,
)
from core.log import get_logger
log = get_logger(__name__)

_client = None
WRITE_BYTES = SAMPLE_RATE // 10 * 2 * CHANNELS


def _get_client():
    global _client
    if _client is None:
        _client = FishAudio(api_key=FISH_API_KEY)
    return _client


def _tts_config(fmt: str = "wav") -> TTSConfig:
    if fmt == "pcm":
        return TTSConfig(reference_id=VOICE_ID, format="pcm", sample_rate=SAMPLE_RATE, latency="balanced")
    return TTSConfig(reference_id=VOICE_ID, format="wav", latency="balanced")


def _rms_level(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean((samples.astype(np.float32) / 32768.0) ** 2)))
    return min(1.0, rms * 5.0)


class AudioOut:
    def __init__(self, persistent: bool = True):
        self.persistent = persistent
        self._queue: queue.Queue = queue.Queue()
        self._idle = threading.Event()
        self._idle.set()
        self._stream = None
        self._lock = threading.Lock()
        self._generation = 0
        self._pending = 0
        self._closed = False
        self.level = 0.0
        self._thread = threading.Thread(target=self._run, daemon=True, name="mara-audio-out")
        self._thread.start()

    def _open(self):
        if self._stream is None:
            self._stream = sd.OutputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16")
            self._stream.start()
        return self._stream

    def _release(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                log.debug(f"[Audio] close failed: {e}")
            self._stream = None

    def _run(self):
        while True:
            item = self._queue.get()
            if item is None:
                break
            generation, pcm = item
            if generation == self._generation:
                try:
                    with self._lock:
                        stream = self._open()
                        metrics.mark("first_audio")
                        samples = np.frombuffer(pcm, dtype=np.int16)
                        self.level = _rms_level(samples)
                        stream.write(samples)
                except Exception as e:
                    log.warning(f"[Audio] playback failed: {e}")
            self._done_one()
        with self._lock:
            self._release()

    def _done_one(self):
        with self._lock:
            self._pending = max(0, self._pending - 1)
            idle = self._pending == 0
            if idle and not self.persistent:
                self._release()
        if idle:
            self.level = 0.0
            system.set_speaking(False)
            self._idle.set()

    def write(self, pcm: bytes):
        if len(pcm) % 2:
            pcm = pcm[:-1]
        if not pcm or self._closed:
            return
        pieces = [pcm[i:i + WRITE_BYTES] for i in range(0, len(pcm), WRITE_BYTES)]
        with self._lock:
            self._pending += len(pieces)
            self._idle.clear()
            system.set_speaking(True)
            for piece in pieces:
                self._queue.put((self._generation, piece))

    def clear(self):
        self.level = 0.0
        with self._lock:
            self._generation += 1
            if self._stream is not None:
                try:
                    self._stream.abort()
                    self._stream.start()
                except Exception as e:
                    log.debug(f"[Audio] abort failed: {e}")
                    self._release()

    def wait_idle(self, timeout: float | None = None) -> bool:
        return self._idle.wait(timeout)

    def close(self):
        self._closed = True
        self._generation += 1
        self._queue.put(None)


_audio_out: AudioOut | None = None


def audio_out() -> AudioOut:
    global _audio_out
    if _audio_out is None:
        _audio_out = AudioOut(persistent=PERSISTENT_AUDIO_OUT)
    return _audio_out


def output_level() -> float:
    return _audio_out.level if _audio_out is not None else 0.0


def close_audio():
    global _audio_out
    if _audio_out is not None:
        _audio_out.close()
        _audio_out = None


class TTSChunker:
    def __init__(self, first_words: int = TTS_FIRST_CHUNK_WORDS, max_words: int = 40):
        self._first_words = first_words
        self._first_done = False
        self._pending = ""
        self._sentences = SentenceBuffer(max_words=max_words)

    def feed(self, delta: str) -> list[str]:
        if self._first_done:
            return [c for c in self._sentences.feed(delta) if c]
        self._pending += delta
        m = re.search(r"[,;:.!?…،؟](?=\s)", self._pending)
        words = self._pending.split()
        if m:
            head, rest = self._pending[:m.end()], self._pending[m.end():]
        elif len(words) > self._first_words:
            cut = self._pending.rstrip().rfind(" ")
            head, rest = self._pending[:cut], self._pending[cut:]
        else:
            return []
        self._first_done = True
        self._pending = ""
        out = [head.strip()] if head.strip() else []
        return out + [c for c in self._sentences.feed(rest) if c]

    def flush(self) -> list[str]:
        if not self._first_done:
            self._first_done = True
            rest, self._pending = self._pending, ""
            return [rest.strip()] if rest.strip() else []
        return self._sentences.flush()


class _Speech:
    def __init__(self, out: AudioOut | None = None):
        self.out = out or audio_out()
        self._texts: queue.Queue = queue.Queue()
        self._filter = SpokenFilter()
        self.cancelled = threading.Event()
        self.failed = None
        self._thread = threading.Thread(target=self._safe_run, daemon=True, name="mara-tts")
        self._thread.start()

    def _texts_iter(self):
        while True:
            item = self._texts.get()
            if item is None or self.cancelled.is_set():
                return
            yield item

    def _safe_run(self):
        try:
            self._run()
        except Exception as e:
            if not self.cancelled.is_set():
                log.exception("[Voice] speech failed")
                self.failed = f"Voice output failed ({type(e).__name__}). Replies are still shown here."

    def feed(self, text: str):
        if self.cancelled.is_set():
            return
        spoken = self._filter.feed(text)
        if spoken:
            self._texts.put(spoken)

    def end(self, timeout: float | None = None):
        self._texts.put(None)
        self._thread.join(timeout)
        if self._thread.is_alive() or (not self.cancelled.is_set() and not self.out.wait_idle(timeout)):
            log.warning("[Voice] speech did not finish in time, cancelling it")
            self.cancel()

    def cancel(self):
        self.cancelled.set()
        self._texts.put(None)
        self.out.clear()


class SentenceSpeech(_Speech):
    def _run(self):
        splitter = SentenceBuffer(soft_min_words=MIN_WORDS_SOFT)
        for chunk in self._texts_iter():
            for sentence in splitter.feed(chunk):
                self._say(sentence)
        if not self.cancelled.is_set():
            for sentence in splitter.flush():
                self._say(sentence)

    def _say(self, sentence: str):
        if self.cancelled.is_set():
            return
        try:
            _synthesize_sentence(sentence, self.out.write, self.cancelled)
        except Exception as e:
            log.exception("[Voice] Synthesis error")
            self.failed = f"Voice output failed ({type(e).__name__}). Replies are still shown here."


class StreamingSpeech(_Speech):
    def _events(self):
        chunker = TTSChunker()
        for delta in self._texts_iter():
            for chunk in chunker.feed(delta):
                text = clean_text(chunk)
                if text:
                    yield text + " "
                    yield FlushEvent()
        if not self.cancelled.is_set():
            for chunk in chunker.flush():
                text = clean_text(chunk)
                if text:
                    yield text
                    yield FlushEvent()

    def _run(self):
        carry = b""
        for audio in _get_client().tts.stream_websocket(self._events(), config=_tts_config("pcm")):
            if self.cancelled.is_set():
                break
            data = carry + audio
            if len(data) % 2:
                carry, data = data[-1:], data[:-1]
            else:
                carry = b""
            self.out.write(data)


def make_speech() -> _Speech:
    if system.is_silent():
        return SilentSpeech()
    return StreamingSpeech() if STREAMING_TTS else SentenceSpeech()


class SilentSpeech:
    failed = None

    def feed(self, text):
        pass

    def end(self, timeout=None):
        pass

    def cancel(self):
        pass


def _synthesize_sentence(sentence: str, write, cancelled: threading.Event | None = None):
    sentence = clean_text(sentence)
    if not sentence:
        return
    header_skipped = False
    header_buffer = b""
    carry = b""
    for audio_chunk in _get_client().tts.stream_websocket(iter([sentence]), config=_tts_config("wav")):
        if cancelled is not None and cancelled.is_set():
            return
        if not header_skipped:
            header_buffer += audio_chunk
            if len(header_buffer) < 44:
                continue
            audio_chunk = header_buffer[44:]
            header_skipped = True
        data = carry + audio_chunk
        if len(data) % 2:
            carry, data = data[-1:], data[:-1]
        else:
            carry = b""
        if data:
            write(data)


def speak(text: str):
    if system.is_silent():
        log.debug(f"[Silent] {text}")
        return
    text = clean_text(text)
    if not text:
        return
    try:
        system.set_speaking(True)
        audio = _get_client().tts.convert(text=text, config=_tts_config("wav"))
        pcm = pcm16_from_wav(bytes(audio))
        if not pcm:
            log.warning("[Voice] TTS returned no audio")
            return
        out = audio_out()
        out.write(pcm)
        out.wait_idle(60)
    except Exception:
        log.exception("[Voice] speak() failed")
    finally:
        system.set_speaking(False)

import math
import queue
import threading
import time
from collections import deque

import numpy as np
import sounddevice as sd
import keyboard
from core import system, metrics
from core.config import (
    TRIGGER_KEY, WHISPER_MODEL, STT_SAMPLE_RATE as SAMPLE_RATE, STT_CHUNK_SIZE as CHUNK_SIZE, LIVE_TRANSCRIPTION,
    PERSISTENT_MIC, MIC_PREROLL_SECONDS, MIN_RECORDING_SECONDS, MIN_RECORDING_LEVEL, BARGE_IN,
)
from core.events import StateChanged, State, MicLevel, UserTranscript, Error
from core.log import get_logger
log = get_logger(__name__)
startup_log = get_logger("startup")

PARTIAL_INTERVAL = 1.2
WHISPER_PROMPT = "MARA."

model = None
_model_ready = threading.Event()
_whisper_lock = threading.Lock()
_hook = None
_barge_in = None
_mic = None


def _load_whisper():
    global model
    startup_log.info("Loading Whisper...")
    try:
        import whisper
        model = whisper.load_model(WHISPER_MODEL)
    except Exception as e:
        log.exception("[Listener] Whisper failed to load")
        _emit(Error(f"Speech recognition could not start ({type(e).__name__}). Typing still works; see mara.log."))
        return
    startup_log.info(f"Whisper ready ({model.device.type})")
    try:
        with _whisper_lock:
            _transcribe(np.zeros(SAMPLE_RATE, dtype=np.int16))
        log.info("[Listener] Whisper warmed up")
    except Exception as e:
        log.warning(f"[Listener] Whisper warm-up failed: {e}")
    _model_ready.set()
    startup_log.info(f"Ready. Hold {TRIGGER_KEY.upper()} to speak.")


def start():
    threading.Thread(target=_load_whisper, daemon=True, name="mara-whisper").start()


def set_event_hook(fn):
    global _hook
    _hook = fn


def set_barge_in(fn):
    global _barge_in
    _barge_in = fn


def _emit(event):
    if _hook is not None:
        try:
            _hook(event)
        except Exception:
            log.exception("[Listener] event hook failed")


def mic_level(chunk: np.ndarray) -> float:
    if chunk.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean((chunk.astype(np.float32) / 32768.0) ** 2)))
    return min(1.0, rms * 12.0)


def should_transcribe(audio: np.ndarray, rate: int = SAMPLE_RATE) -> bool:
    if audio.size < MIN_RECORDING_SECONDS * rate:
        return False
    rms = float(np.sqrt(np.mean((audio.astype(np.float32) / 32768.0) ** 2)))
    return rms >= MIN_RECORDING_LEVEL


def _transcribe(audio_int16: np.ndarray) -> dict:
    audio = audio_int16.astype(np.float32) / 32768.0
    return model.transcribe(audio, language=None, task="transcribe", condition_on_previous_text=False,
                            initial_prompt=WHISPER_PROMPT, fp16=model.device.type == "cuda")


class MicInput:
    def __init__(self, preroll_seconds: float = MIC_PREROLL_SECONDS, stream_factory=None):
        self._lock = threading.Lock()
        self._preroll: deque = deque(maxlen=max(1, math.ceil(preroll_seconds * SAMPLE_RATE / CHUNK_SIZE)))
        self._recording: list | None = None
        self._fresh: queue.Queue = queue.Queue()
        factory = stream_factory or (lambda cb: sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=CHUNK_SIZE, callback=cb))
        self._stream = factory(self._callback)
        self._stream.start()

    def _callback(self, indata, frames, time_info, status):
        chunk = np.array(indata, dtype=np.int16).reshape(-1).copy()
        with self._lock:
            if self._recording is None:
                self._preroll.append(chunk)
            else:
                self._recording.append(chunk)
                self._fresh.put(chunk)

    def begin(self):
        with self._lock:
            self._recording = list(self._preroll)
            self._preroll.clear()
            self._fresh = queue.Queue()

    def next_chunk(self, timeout: float = 0.1) -> np.ndarray | None:
        try:
            return self._fresh.get(timeout=timeout)
        except queue.Empty:
            return None

    def snapshot(self) -> np.ndarray:
        with self._lock:
            chunks = list(self._recording or [])
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)

    def end(self) -> np.ndarray:
        with self._lock:
            chunks, self._recording = self._recording or [], None
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.int16)

    def close(self):
        try:
            self._stream.stop()
            self._stream.close()
        except Exception as e:
            log.debug(f"[Listener] mic close failed: {e}")


class _OneShotMic:
    def __init__(self):
        self._chunks: list = []
        self._stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=CHUNK_SIZE)

    def begin(self):
        self._stream.start()

    def next_chunk(self, timeout: float = 0.1) -> np.ndarray | None:
        chunk, _ = self._stream.read(CHUNK_SIZE)
        chunk = np.frombuffer(chunk, dtype=np.int16).copy()
        self._chunks.append(chunk)
        return chunk

    def snapshot(self) -> np.ndarray:
        return np.concatenate(self._chunks) if self._chunks else np.zeros(0, dtype=np.int16)

    def end(self) -> np.ndarray:
        self._stream.stop()
        self._stream.close()
        return self.snapshot()


def _get_mic():
    global _mic
    if not PERSISTENT_MIC:
        return _OneShotMic()
    if _mic is None:
        _mic = MicInput()
    return _mic


def close():
    global _mic
    if _mic is not None:
        _mic.close()
        _mic = None


class _Partial:
    def __init__(self):
        self.active = True
        self.running = False

    def run(self, audio: np.ndarray):
        if not _whisper_lock.acquire(blocking=False):
            self.running = False
            return
        try:
            text = _transcribe(audio)["text"].strip()
            if self.active and text:
                _emit(UserTranscript(text, final=False))
        except Exception as e:
            log.debug(f"[Listener] partial transcription failed: {e}")
        finally:
            _whisper_lock.release()
            self.running = False


def _record(mic) -> np.ndarray:
    start = time.monotonic()
    last_partial = start
    partial = _Partial()
    mic.begin()
    while keyboard.is_pressed(TRIGGER_KEY):
        chunk = mic.next_chunk()
        if chunk is None:
            continue
        now = time.monotonic()
        _emit(MicLevel(mic_level(chunk), now - start))
        if LIVE_TRANSCRIPTION and not partial.running and now - last_partial >= PARTIAL_INTERVAL:
            last_partial = now
            partial.running = True
            threading.Thread(target=partial.run, args=(mic.snapshot(),), daemon=True).start()
    partial.active = False
    return mic.end()


def listen() -> str:
    _model_ready.wait()
    log.info(f"Hold {TRIGGER_KEY.upper()} to talk...")
    keyboard.wait(TRIGGER_KEY, suppress=True)

    if BARGE_IN and _barge_in is not None:
        _barge_in()
    elif system.is_speaking():
        return ""

    _emit(StateChanged(State.LISTENING))
    _emit(UserTranscript("", final=False))
    audio = _record(_get_mic())
    metrics.start("voice")
    _emit(StateChanged(State.THINKING))

    text = ""
    if should_transcribe(audio):
        with _whisper_lock:
            result = _transcribe(audio)
        metrics.mark("whisper_done")
        text = result.get("text", "").strip()
        system.set_current_lang(result.get("language", ""))
    else:
        log.info("[Listener] Recording too short or too quiet, ignored.")

    if text:
        log.debug(f"Heard: {text}")
    else:
        metrics.discard()
        _emit(UserTranscript("", final=True))
    return text

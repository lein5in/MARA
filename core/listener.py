import os
import tempfile
import threading
import time
import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wav
import whisper
import keyboard
from core import system
from core.config import (
    TRIGGER_KEY, WHISPER_MODEL, STT_SAMPLE_RATE as SAMPLE_RATE, STT_CHUNK_SIZE as CHUNK_SIZE, LIVE_TRANSCRIPTION,
)
from core.events import StateChanged, State, MicLevel, UserTranscript
from core.log import get_logger
log = get_logger(__name__)
startup_log = get_logger("startup")

PARTIAL_INTERVAL = 1.2
WHISPER_PROMPT = "MARA assistant vocal personnel."

startup_log.info("Loading Whisper...")
model = None
_model_ready = threading.Event()
_whisper_lock = threading.Lock()
_hook = None


def _load_whisper():
    global model
    model = whisper.load_model(WHISPER_MODEL)
    _model_ready.set()
    startup_log.info(f"Whisper ready ({model.device.type})")
    startup_log.info(f"Ready. Hold {TRIGGER_KEY.upper()} to speak.")


threading.Thread(target=_load_whisper, daemon=True).start()


def set_event_hook(fn):
    global _hook
    _hook = fn


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


def _transcribe_array(audio_int16: np.ndarray) -> dict:
    audio = audio_int16.astype(np.float32) / 32768.0
    return model.transcribe(audio, language=None, task="transcribe", condition_on_previous_text=False,
                            initial_prompt=WHISPER_PROMPT, fp16=model.device.type == "cuda")


class _Partial:
    def __init__(self):
        self.active = True
        self.running = False

    def run(self, audio: np.ndarray):
        if not _whisper_lock.acquire(blocking=False):
            self.running = False
            return
        try:
            text = _transcribe_array(audio)["text"].strip()
            if self.active and text:
                _emit(UserTranscript(text, final=False))
        except Exception as e:
            log.debug(f"[Listener] partial transcription failed: {e}")
        finally:
            _whisper_lock.release()
            self.running = False


def listen() -> str:
    _model_ready.wait()
    log.info(f"Hold {TRIGGER_KEY.upper()} to talk...")
    keyboard.wait(TRIGGER_KEY, suppress=True)

    if system.is_speaking():
        return ""

    _emit(StateChanged(State.LISTENING))
    _emit(UserTranscript("", final=False))
    audio_chunks = []
    start = time.monotonic()
    last_partial = start
    partial = _Partial()

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16', blocksize=CHUNK_SIZE) as stream:
        while keyboard.is_pressed(TRIGGER_KEY):
            chunk, _ = stream.read(CHUNK_SIZE)
            chunk_np = np.frombuffer(chunk, dtype=np.int16).copy()
            audio_chunks.append(chunk_np)
            now = time.monotonic()
            _emit(MicLevel(mic_level(chunk_np), now - start))
            if LIVE_TRANSCRIPTION and not partial.running and now - last_partial >= PARTIAL_INTERVAL:
                last_partial = now
                partial.running = True
                threading.Thread(target=partial.run, args=(np.concatenate(audio_chunks),), daemon=True).start()
    partial.active = False
    _emit(StateChanged(State.THINKING))

    text = ""
    if audio_chunks:
        full_audio = np.concatenate(audio_chunks)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                temp_path = f.name
            wav.write(temp_path, SAMPLE_RATE, full_audio)
            with _whisper_lock:
                result = model.transcribe(temp_path, language=None, task="transcribe",
                                          condition_on_previous_text=False, initial_prompt=WHISPER_PROMPT)
            text = result["text"].strip()
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    if text:
        log.debug(f"Heard: {text}")
    else:
        _emit(UserTranscript("", final=True))
        _emit(StateChanged(State.IDLE))
    return text

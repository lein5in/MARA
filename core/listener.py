import os
import tempfile
import threading
import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wav
import whisper
import keyboard
from core import system
from core.config import TRIGGER_KEY, WHISPER_MODEL, STT_SAMPLE_RATE as SAMPLE_RATE, STT_CHUNK_SIZE as CHUNK_SIZE
from core.log import get_logger
log = get_logger(__name__)
startup_log = get_logger("startup")


startup_log.info("Loading Whisper...")
model = None
_model_ready = threading.Event()

def _load_whisper():
    global model
    model = whisper.load_model(WHISPER_MODEL)
    _model_ready.set()
    startup_log.info(f"Whisper ready ({model.device.type})")
    startup_log.info(f"Ready. Hold {TRIGGER_KEY.upper()} to speak.")

threading.Thread(target=_load_whisper, daemon=True).start()




_whisper_lock = threading.Lock()



def listen() -> str:
    """
    Attend que F13 (bouton sniper G502) soit maintenu.
    Enregistre tant que le bouton est pressé, transcrit au relâchement.
    """
    _model_ready.wait()

    log.info("Maintiens le bouton souris pour parler...")

    
    keyboard.wait(TRIGGER_KEY, suppress=True)

    
    if system.is_speaking():
        return ""

    log.info("🎙️ J'écoute...")
    audio_chunks = []

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype='int16',
        blocksize=CHUNK_SIZE
    ) as stream:
        while keyboard.is_pressed(TRIGGER_KEY):
            chunk, _ = stream.read(CHUNK_SIZE)
            chunk_np = np.frombuffer(chunk, dtype=np.int16)
            audio_chunks.append(chunk_np)

    log.info("Traitement...")

    if not audio_chunks:
        return ""

    full_audio = np.concatenate(audio_chunks)
    temp_path  = None

    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name
        wav.write(temp_path, SAMPLE_RATE, full_audio)

        with _whisper_lock:
            result = model.transcribe(
                temp_path,
                language=None,
                task="transcribe",
                condition_on_previous_text=False,
                initial_prompt="MARA assistant vocal personnel."
            )
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    text = result["text"].strip()
    if text:
        log.debug(f"Tu as dit : {text}")
    return text
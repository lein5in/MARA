import os
import tempfile
import threading
import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wav
import whisper
import keyboard


print("Chargement de Whisper...")
model = None
_model_ready = threading.Event()

def _load_whisper():
    global model
    model = whisper.load_model("turbo")
    _model_ready.set()
    print("Whisper prêt.")

threading.Thread(target=_load_whisper, daemon=True).start()


SAMPLE_RATE    = 16000
CHUNK_SIZE     = 512
TRIGGER_KEY    = "f13"   


_whisper_lock = threading.Lock()


_is_speaking   = False
_speaking_lock = threading.Lock()

def set_speaking(val: bool):
    """
    Appelé par voice.py avant/après chaque playback TTS.
    Thread-safe — évite que le listener capte la voix de MARA.
    """
    global _is_speaking
    with _speaking_lock:
        _is_speaking = val

def _get_is_speaking() -> bool:
    with _speaking_lock:
        return _is_speaking



def listen() -> str:
    """
    Attend que F13 (bouton sniper G502) soit maintenu.
    Enregistre tant que le bouton est pressé, transcrit au relâchement.
    """
    _model_ready.wait()

    print("Maintiens le bouton souris pour parler...")

    
    keyboard.wait(TRIGGER_KEY, suppress=True)

    
    if _get_is_speaking():
        return ""

    print("🎙️ J'écoute...")
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

    print("Traitement...")

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
        print(f"Tu as dit : {text}")
    return text
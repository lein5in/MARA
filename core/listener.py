import whisper
import sounddevice as sd
import numpy as np
import tempfile
import scipy.io.wavfile as wav
import keyboard

print("Chargement de Whisper...")
model = whisper.load_model("turbo")
print("Whisper prêt.")

SAMPLE_RATE = 16000
CHUNK_SIZE = 512

def listen() -> str:
    """
    Enregistre l'audio tant que Enter est maintenu.
    Transcrit dès que Enter est relâché.
    """
    print("Maintiens ENTRÉE pour parler, relâche pour envoyer...")

    # Attendre que Enter soit maintenu
    keyboard.wait("enter", suppress=True)
    
    print("🎙️ J'écoute...")
    audio_chunks = []

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16', blocksize=CHUNK_SIZE) as stream:
        while keyboard.is_pressed("enter"):
            chunk, _ = stream.read(CHUNK_SIZE)
            chunk_np = np.frombuffer(chunk, dtype=np.int16)
            audio_chunks.append(chunk_np)

    print("Traitement...")

    if not audio_chunks:
        return ""

    full_audio = np.concatenate(audio_chunks)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav.write(f.name, SAMPLE_RATE, full_audio)
        result = model.transcribe(
            f.name,
            language=None,
            task="transcribe",
            condition_on_previous_text=False,
            initial_prompt="MARA assistant vocal personnel."
        )

    text = result["text"].strip()
    print(f"Tu as dit : {text}")
    return text
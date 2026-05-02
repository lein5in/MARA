import os
import re
import time
import tempfile
import threading
import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wav
import whisper
import keyboard
from collections import deque

print("Chargement de Whisper...")
model = whisper.load_model("turbo")
print("Whisper prêt.")

SAMPLE_RATE = 16000
CHUNK_SIZE  = 512

# ─── Lock Whisper — GPU ne peut pas transcrire en parallèle ───────────────────
_whisper_lock = threading.Lock()

# ─── Paramètres réveil d'urgence ──────────────────────────────────────────────
_ENERGY_THRESHOLD  = 600    # RMS minimum — plus élevé pour éviter les faux positifs
_BUFFER_SECONDS    = 1.5    # durée du buffer à transcrire quand voix détectée
_DETECTION_WINDOW  = 8      # secondes pour compter 3x "MARA"
_REQUIRED_COUNT    = 3      # nombre de "MARA" requis pour le réveil
_COOLDOWN_SECONDS  = 2      # pause entre deux transcriptions d'urgence
_POST_WAKE_COOLDOWN = 8.0   # secondes d'immunité après un réveil d'urgence
_POST_PAUSE_GRACE  = 4.0    # secondes d'immunité après la mise en pause (évite le tail audio)


# ══════════════════════════════════════════════════════════════════════════════
# LISTENER PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def listen() -> str:
    """
    Écoute tant que l'utilisateur maintient ENTRÉE, transcrit au relâchement.
    Utilise le lock Whisper pour éviter les conflits GPU avec l'emergency listener.
    """
    print("Maintiens ENTRÉE pour parler, relâche pour envoyer...")

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
            os.unlink(temp_path)

    text = result["text"].strip()
    print(f"Tu as dit : {text}")
    return text


# ══════════════════════════════════════════════════════════════════════════════
# EMERGENCY LISTENER
# ══════════════════════════════════════════════════════════════════════════════

def _compute_rms(audio: np.ndarray) -> float:
    """Calcule le niveau d'énergie RMS du signal audio."""
    return float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))


def _transcribe_buffer(audio: np.ndarray) -> str:
    """
    Transcrit un buffer audio court avec Whisper.
    Utilise le lock — ne bloque jamais le listener principal longtemps.
    Retourne le texte en minuscules, ou "" si échec.
    """
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_path = f.name
            wav.write(temp_path, SAMPLE_RATE, audio)

        # Essaie d'acquérir le lock sans bloquer indéfiniment
        acquired = _whisper_lock.acquire(timeout=2.0)
        if not acquired:
            return ""

        try:
            result = model.transcribe(
                temp_path,
                language=None,
                task="transcribe",
                condition_on_previous_text=False,
                initial_prompt="MARA."
            )
            return result["text"].strip().lower()
        finally:
            _whisper_lock.release()

    except Exception as e:
        print(f"[Emergency] Erreur transcription : {e}")
        return ""
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except Exception:
                pass


def _emergency_loop(on_wake, stop_event: threading.Event):
    """
    Boucle principale du thread d'urgence.
    Écoute en continu, détecte "MARA" x3 dans la fenêtre de temps.
    """
    buffer_size   = int(SAMPLE_RATE * _BUFFER_SECONDS)
    rolling_audio = deque(maxlen=buffer_size)
    detections    = deque()
    last_check    = 0.0
    # Grâce période au démarrage — laisse le temps à l'audio de se stabiliser
    immune_until  = time.time() + _POST_PAUSE_GRACE

    print("[Emergency] Thread de réveil d'urgence démarré.")

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype='int16',
            blocksize=CHUNK_SIZE
        ) as stream:

            while not stop_event.is_set():
                chunk, _ = stream.read(CHUNK_SIZE)
                chunk_np = np.frombuffer(chunk, dtype=np.int16)
                rolling_audio.extend(chunk_np.tolist())

                now = time.time()

                # Période d'immunité — ignore tout (post-pause ou post-wake)
                if now < immune_until:
                    continue

                # Cooldown entre transcriptions
                if now - last_check < _COOLDOWN_SECONDS:
                    continue

                if len(rolling_audio) < buffer_size:
                    continue

                audio_array = np.array(rolling_audio, dtype=np.int16)
                rms = _compute_rms(audio_array)

                if rms < _ENERGY_THRESHOLD:
                    continue

                # Voix détectée — transcription
                last_check = now
                text = _transcribe_buffer(audio_array)

                if not text:
                    continue

                mara_count = len(re.findall(r'\bmara\b', text))

                if mara_count > 0:
                    detections.append(now)
                    print(f"[Emergency] 'MARA' détecté ({len(detections)}/{_REQUIRED_COUNT}) — \"{text}\"")

                # Nettoie les détections hors fenêtre
                while detections and (now - detections[0]) > _DETECTION_WINDOW:
                    detections.popleft()

                # 3 détections dans la fenêtre → réveil d'urgence
                if len(detections) >= _REQUIRED_COUNT:
                    print("[Emergency] ⚡ Réveil d'urgence déclenché !")
                    detections.clear()
                    rolling_audio.clear()
                    last_check   = now
                    immune_until = now + _POST_WAKE_COOLDOWN  # immunité post-wake
                    try:
                        on_wake()
                    except Exception as e:
                        print(f"[Emergency] Erreur callback réveil : {e}")

    except Exception as e:
        if not stop_event.is_set():
            print(f"[Emergency] Erreur boucle d'urgence : {e}")

    print("[Emergency] Thread arrêté.")


def start_emergency_listener(on_wake) -> threading.Event:
    """
    Démarre le thread de réveil d'urgence en arrière-plan.

    Args:
        on_wake: callable appelé quand "MARA" est dit 3x en moins de 8 secondes.
                 Doit être thread-safe (pas d'accès UI direct).

    Returns:
        stop_event: threading.Event — appelle stop_event.set() pour arrêter le thread.

    Usage dans main.py :
        from core.listener import start_emergency_listener
        stop_event = start_emergency_listener(on_emergency_wake)
        # Pour arrêter : stop_event.set()
    """
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_emergency_loop,
        args=(on_wake, stop_event),
        daemon=True,
        name="MARA-EmergencyListener"
    )
    thread.start()
    return stop_event
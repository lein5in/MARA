import os
import re
import threading
import queue
import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from fishaudio import FishAudio
from fishaudio.types import TTSConfig
from core.listener import set_speaking
from core import system

load_dotenv()

FISH_API_KEY = os.getenv("FISH_API_KEY")
VOICE_ID =  "26e416bca5c74c5db7d6dd5a49caee13"

client = FishAudio(api_key=FISH_API_KEY)

SAMPLE_RATE = 44100
CHANNELS = 1

def clean_text(text: str) -> str:
    text = re.sub(r'\*\*?(.*?)\*\*?', r'\1', text)
    text = re.sub(r'#{1,6}\s', '', text)
    text = re.sub(r'`{1,3}.*?`{1,3}', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'^\s*[-•]\s', '', text, flags=re.MULTILINE)
    text = re.sub(r'[^\x00-\x7F\u00C0-\u024F\u1E00-\u1EFF]', '', text)
    text = re.sub(r'\b[A-Z]{2,}\b', lambda m: m.group().lower(), text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def play_pcm_stream(audio_queue):
    with sd.OutputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='int16') as stream:
        while True:
            chunk = audio_queue.get()
            if chunk is None:
                break
            samples = np.frombuffer(chunk, dtype=np.int16)
            stream.write(samples)

def speak(text: str):
    """
    Convertit le texte en audio et le joue.
    Skip silencieusement si le silent mode est actif.
    """
    if system.is_silent():
        print(f"[Silent] {text}")
        return
    try:
        set_speaking(True)
        config = TTSConfig(
            reference_id=VOICE_ID,
            format="wav",
            latency="balanced"
        )
        audio_data = b""
        for chunk in client.tts.convert(text=clean_text(text), config=config):
            audio_data += chunk
        pcm_data = audio_data[44:]
        samples = np.frombuffer(pcm_data, dtype=np.int16)
        sd.play(samples, samplerate=SAMPLE_RATE)
        sd.wait()
    except Exception as e:
        print(f"Erreur Fish Audio : {e}")
    finally:
        set_speaking(False)

def speak_stream(text_generator):
    """
    Stream le texte vers Fish Audio via WebSocket.
    Skip silencieusement si le silent mode est actif — consomme quand même
    le générateur pour ne pas bloquer le pipeline.
    """
    full_text = ""

    if system.is_silent():
        for chunk in text_generator:
            full_text += chunk
        print(f"[Silent] {full_text}")
        return full_text

    audio_queue = queue.Queue()
    header_skipped = False
    header_buffer = b""

    def text_chunks():
        nonlocal full_text
        for chunk in text_generator:
            full_text += chunk
            cleaned = clean_text(chunk)
            if cleaned:
                yield cleaned

    set_speaking(True)

    playback_thread = threading.Thread(
        target=play_pcm_stream,
        args=(audio_queue,),
        daemon=True
    )
    playback_thread.start()

    try:
        config = TTSConfig(
            reference_id=VOICE_ID,
            format="wav",
            latency="balanced"
        )
        for audio_chunk in client.tts.stream_websocket(text_chunks(), config=config):
            if not header_skipped:
                header_buffer += audio_chunk
                if len(header_buffer) >= 44:
                    audio_queue.put(header_buffer[44:])
                    header_skipped = True
            else:
                audio_queue.put(audio_chunk)
    except Exception as e:
        print(f"Erreur Fish Audio stream : {e}")

    audio_queue.put(None)
    playback_thread.join()
    set_speaking(False)

    return full_text
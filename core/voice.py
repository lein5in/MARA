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
VOICE_ID = "26e416bca5c74c5db7d6dd5a49caee13"

client = FishAudio(api_key=FISH_API_KEY)

SAMPLE_RATE = 44100
CHANNELS = 1

# Minimum number of words before sending a chunk ending with a soft delimiter (comma)
MIN_WORDS_SOFT = 8


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


def play_pcm_stream(audio_queue: queue.Queue):
    """Plays PCM int16 chunks from a queue until it receives None."""
    with sd.OutputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='int16') as stream:
        while True:
            chunk = audio_queue.get()
            if chunk is None:
                break
            samples = np.frombuffer(chunk, dtype=np.int16)
            stream.write(samples)


def _synthesize_sentence(sentence: str, audio_queue: queue.Queue):
    """
    Sends a single sentence to Fish Audio and pushes PCM chunks into audio_queue.
    Skips the 44-byte WAV header on the first audio chunk.
    """
    sentence = clean_text(sentence)
    if not sentence:
        return

    config = TTSConfig(
        reference_id=VOICE_ID,
        format="wav",
        latency="balanced"
    )

    header_skipped = False
    header_buffer = b""

    for audio_chunk in client.tts.stream_websocket(iter([sentence]), config=config):
        if not header_skipped:
            header_buffer += audio_chunk
            if len(header_buffer) >= 44:
                audio_queue.put(header_buffer[44:])
                header_skipped = True
        else:
            audio_queue.put(audio_chunk)


def speak(text: str):
    """
    One-shot TTS for short, pre-built strings (confirmations, memory replies, etc.).
    Skips silently if silent mode is active.
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
    Legacy wrapper — kept for callers that pass a single-item iterator
    (e.g. speak_stream(iter([msg]))).
    Collects all text and delegates to speak_stream_sentences.
    """
    def _gen():
        for chunk in text_generator:
            yield chunk

    return speak_stream_sentences(_gen())


def speak_stream_sentences(text_generator):
    """
    Core streaming TTS.

    Pipeline:
        Claude chunks → sentence buffer → Fish Audio (per sentence) → PCM queue → sounddevice

    Fish Audio starts synthesising the FIRST sentence while Claude is still
    generating the rest — perceived latency drops from ~3 s to ~0.8 s.

    Hard delimiters  → always flush:  .  !  ?
    Soft delimiters  → flush only after MIN_WORDS_SOFT words:  ,  ;  :
    Fallback         → flush every 40 words even without punctuation.

    Returns the full concatenated text so callers can use it for JSON parsing.
    """
    full_text = ""

    if system.is_silent():
        for chunk in text_generator:
            full_text += chunk
        print(f"[Silent] {full_text}")
        return full_text

    audio_queue: queue.Queue = queue.Queue()

    # Start the audio playback thread immediately — it blocks on the queue.
    playback_thread = threading.Thread(
        target=play_pcm_stream,
        args=(audio_queue,),
        daemon=True
    )
    playback_thread.start()

    set_speaking(True)

    HARD = re.compile(r'[.!?]+')
    SOFT = re.compile(r'[,;:]+')

    buffer = ""
    word_count = 0

    def flush(sentence: str):
        """Synthesise one sentence in the current thread (sequential sentences)."""
        sentence = sentence.strip()
        if sentence:
            try:
                _synthesize_sentence(sentence, audio_queue)
            except Exception as e:
                print(f"[Voice] Synthesis error: {e}")

    try:
        for chunk in text_generator:
            full_text += chunk
            buffer += chunk
            word_count += len(chunk.split())

            # Hard delimiter → flush immediately
            if HARD.search(buffer):
                parts = HARD.split(buffer)
                # All parts except the last are complete sentences
                for part in parts[:-1]:
                    flush(part)
                buffer = parts[-1]
                word_count = len(buffer.split())

            # Soft delimiter → flush only if enough words accumulated
            elif SOFT.search(buffer) and word_count >= MIN_WORDS_SOFT:
                parts = SOFT.split(buffer)
                for part in parts[:-1]:
                    flush(part)
                buffer = parts[-1]
                word_count = len(buffer.split())

            # Fallback: flush every 40 words to avoid unbounded buffering
            elif word_count >= 40:
                flush(buffer)
                buffer = ""
                word_count = 0

        # Flush whatever remains
        if buffer.strip():
            flush(buffer)

    except Exception as e:
        print(f"[Voice] Stream error: {e}")
    finally:
        audio_queue.put(None)          # Signal playback thread to stop
        playback_thread.join()
        set_speaking(False)

    return full_text
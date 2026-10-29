import threading
import queue
import numpy as np
import sounddevice as sd
from fishaudio import FishAudio
from fishaudio.types import TTSConfig
from core import system
from core.text import clean_text, pcm16_from_wav, SentenceBuffer
from core.config import FISH_API_KEY, VOICE_ID, TTS_SAMPLE_RATE as SAMPLE_RATE, TTS_CHANNELS as CHANNELS, MIN_WORDS_SOFT
from core.log import get_logger
log = get_logger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = FishAudio(api_key=FISH_API_KEY)
    return _client


def _tts_config() -> TTSConfig:
    return TTSConfig(reference_id=VOICE_ID, format="wav", latency="balanced")


def play_pcm_stream(audio_queue: queue.Queue):
    with sd.OutputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='int16') as stream:
        while True:
            chunk = audio_queue.get()
            if chunk is None:
                break
            if len(chunk) % 2:
                chunk = chunk[:-1]
            stream.write(np.frombuffer(chunk, dtype=np.int16))


def _synthesize_sentence(sentence: str, audio_queue: queue.Queue):
    sentence = clean_text(sentence)
    if not sentence:
        return

    header_skipped = False
    header_buffer = b""
    carry = b""

    for audio_chunk in _get_client().tts.stream_websocket(iter([sentence]), config=_tts_config()):
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
            audio_queue.put(data)


def speak(text: str):
    if system.is_silent():
        log.debug(f"[Silent] {text}")
        return
    text = clean_text(text)
    if not text:
        return
    try:
        system.set_speaking(True)
        audio = _get_client().tts.convert(text=text, config=_tts_config())
        pcm = pcm16_from_wav(bytes(audio))
        if not pcm:
            log.warning("[Voice] TTS returned no audio")
            return
        sd.play(np.frombuffer(pcm, dtype=np.int16), samplerate=SAMPLE_RATE)
        sd.wait()
    except Exception:
        log.exception("[Voice] speak() failed")
    finally:
        system.set_speaking(False)


def speak_stream_sentences(text_generator):
    full_text = ""

    if system.is_silent():
        for chunk in text_generator:
            full_text += chunk
        log.debug(f"[Silent] {full_text}")
        return full_text

    audio_queue: queue.Queue = queue.Queue()
    playback_thread = threading.Thread(target=play_pcm_stream, args=(audio_queue,), daemon=True)
    playback_thread.start()
    system.set_speaking(True)

    def flush(sentence: str):
        try:
            _synthesize_sentence(sentence, audio_queue)
        except Exception:
            log.exception("[Voice] Synthesis error")

    splitter = SentenceBuffer(soft_min_words=MIN_WORDS_SOFT)
    try:
        for chunk in text_generator:
            full_text += chunk
            for sentence in splitter.feed(chunk):
                flush(sentence)
        for sentence in splitter.flush():
            flush(sentence)
    except Exception:
        log.exception("[Voice] Stream error")
    finally:
        audio_queue.put(None)
        playback_thread.join()
        system.set_speaking(False)

    return full_text

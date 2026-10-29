import os
from pathlib import Path

from dotenv import load_dotenv

from core.log import setup_logging

load_dotenv()
setup_logging()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
FISH_API_KEY = os.getenv("FISH_API_KEY")
USER_NAME = os.getenv("USER_NAME", "")

MODEL_MAIN = "claude-sonnet-5"
MODEL_VISUAL = "claude-sonnet-4-6"
MODEL_FAST = "claude-haiku-4-5-20251001"

MAX_HISTORY = 20

TRIGGER_KEY = "f13"
WHISPER_MODEL = "turbo"
STT_SAMPLE_RATE = 16000
STT_CHUNK_SIZE = 512

VOICE_ID = "26e416bca5c74c5db7d6dd5a49caee13"
TTS_SAMPLE_RATE = 44100
TTS_CHANNELS = 1
MIN_WORDS_SOFT = 8

WIN_W = 680
WIN_H = 700
ORB_SIZE = 180

BROWSER_TIMEOUT = 10
WINDOW_WAIT_TIMEOUT = 4.0
REGISTRY_SCAN_TIMEOUT = 30

PROJECT_ROOT = Path(__file__).parent.parent
MEMORY_DIR = PROJECT_ROOT / "memory"
REGISTRY_PATH = PROJECT_ROOT / "assets" / "app_registry.json"
KEY_PATH = MEMORY_DIR / "mara.key"
MEMORY_PATH = MEMORY_DIR / "mara_memory.enc"
CREDENTIALS_PATH = MEMORY_DIR / "mara_credentials.enc"
SCREENSHOTS_DIR = Path.home() / "Pictures" / "Screenshots"

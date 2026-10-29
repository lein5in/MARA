import os
from pathlib import Path

from dotenv import load_dotenv

from core.log import setup_logging
from core.storage import migrate_legacy_data

load_dotenv()
setup_logging()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
FISH_API_KEY = os.getenv("FISH_API_KEY")
USER_NAME = os.getenv("USER_NAME", "")

MODEL_MAIN = "claude-sonnet-5"
MODEL_FAST = "claude-haiku-4-5-20251001"

MAX_HISTORY_TURNS = 12
MAX_HISTORY_IMAGES = 2
MAX_TOOL_ITERATIONS = 8
MAX_TOKENS = 1024
API_TIMEOUT = 30.0
API_MAX_RETRIES = 2
CONFIRM_TIMEOUT = 60.0

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
FILE_SEARCH_TIMEOUT = 4.0
FILE_SEARCH_MAX_RESULTS = 5

PROJECT_ROOT = Path(__file__).parent.parent
_DATA_OVERRIDE = os.environ.get("MARA_DATA_DIR")
DATA_DIR = Path(_DATA_OVERRIDE) if _DATA_OVERRIDE else Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "MARA"
LOCAL_DIR = DATA_DIR / "local" if _DATA_OVERRIDE else Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "MARA"
CHROME_PROFILE_DIR = LOCAL_DIR / "ChromeProfile"
REGISTRY_PATH = DATA_DIR / "app_registry.json"
KEY_PATH = DATA_DIR / "mara.key"
MEMORY_PATH = DATA_DIR / "mara_memory.enc"
CREDENTIALS_PATH = DATA_DIR / "mara_credentials.enc"
PROFILE_PATH = DATA_DIR / "profile.md"
PROFILE_EXAMPLE_PATH = PROJECT_ROOT / "profile.example.md"

_LEGACY_MEMORY_DIR = PROJECT_ROOT / "memory"
if _DATA_OVERRIDE:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
else:
    migrate_legacy_data(
        DATA_DIR,
        key=(_LEGACY_MEMORY_DIR / "mara.key", KEY_PATH),
        encrypted=[
            (_LEGACY_MEMORY_DIR / "mara_memory.enc", MEMORY_PATH),
            (_LEGACY_MEMORY_DIR / "mara_credentials.enc", CREDENTIALS_PATH),
        ],
        plain=[(PROJECT_ROOT / "assets" / "app_registry.json", REGISTRY_PATH)],
    )

SCREENSHOTS_DIR = DATA_DIR / "screenshots" if _DATA_OVERRIDE else Path.home() / "Pictures" / "Screenshots"

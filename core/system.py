import re
import subprocess
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from core.config import SCREENSHOTS_DIR
from core.log import get_logger
log = get_logger(__name__)

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    from ctypes import cast, POINTER
    _PYCAW_OK = True
except ImportError:
    _PYCAW_OK = False
    log.warning("[System] pycaw not available, volume control disabled.")

try:
    import screen_brightness_control as sbc
    _SBC_OK = True
except ImportError:
    _SBC_OK = False
    log.warning("[System] screen_brightness_control not available, brightness control disabled.")

try:
    import pyautogui
    _SCREENSHOT_OK = True
except ImportError:
    _SCREENSHOT_OK = False
    log.warning("[System] pyautogui not available, screenshots disabled.")


class SystemActionError(Exception):
    pass


_current_lang = "en"

def set_current_lang(lang: str):
    global _current_lang
    lang = (lang or "").lower().strip()
    if lang in ("fr", "en", "ar"):
        _current_lang = lang

def current_lang() -> str:
    return _current_lang

_is_speaking = threading.Event()

def set_speaking(val: bool):
    if val:
        _is_speaking.set()
    else:
        _is_speaking.clear()

def is_speaking() -> bool:
    return _is_speaking.is_set()

_modes = {"silent": False, "vision": False}
_mode_lock = threading.Lock()

def set_silent(val: bool):
    with _mode_lock:
        _modes["silent"] = bool(val)
    log.info(f"[System] Silent mode {'on' if val else 'off'}.")

def is_silent() -> bool:
    return _modes["silent"]

def set_vision(val: bool):
    with _mode_lock:
        _modes["vision"] = bool(val)
    log.info(f"[System] Vision mode {'on' if val else 'off'}.")

def is_vision() -> bool:
    return _modes["vision"]

_volume_interface = None

def _get_volume_interface():
    global _volume_interface
    if not _PYCAW_OK:
        raise SystemActionError("volume control is not available on this machine")
    if _volume_interface is None:
        import comtypes
        comtypes.CoInitialize()
        devices = AudioUtilities.GetSpeakers()
        interface = devices._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        _volume_interface = cast(interface, POINTER(IAudioEndpointVolume))
    return _volume_interface

def set_volume(level: int) -> int:
    level = max(0, min(100, int(level)))
    _get_volume_interface().SetMasterVolumeLevelScalar(level / 100.0, None)
    return level

def get_volume() -> tuple[int, bool]:
    vol = _get_volume_interface()
    return round(vol.GetMasterVolumeLevelScalar() * 100), bool(vol.GetMute())

def set_mute(muted: bool):
    _get_volume_interface().SetMute(1 if muted else 0, None)

def set_brightness(level: int) -> int:
    if not _SBC_OK:
        raise SystemActionError("brightness control is not available on this machine")
    level = max(0, min(100, int(level)))
    sbc.set_brightness(level)
    return level

def get_brightness() -> int:
    if not _SBC_OK:
        raise SystemActionError("brightness control is not available on this machine")
    level = sbc.get_brightness()
    if isinstance(level, list):
        level = level[0]
    return int(level)

def _netsh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["netsh", "wlan", *args], capture_output=True, text=True, timeout=15)

def wifi_disconnect() -> str:
    result = _netsh("disconnect")
    if result.returncode != 0:
        raise SystemActionError(result.stderr.strip() or result.stdout.strip() or "netsh failed")
    return "WiFi disconnected."

def wifi_connect(ssid: str | None = None) -> str:
    if not ssid:
        profiles = re.findall(r"All User Profile\s*:\s*(.+)", _netsh("show", "profiles").stdout)
        if not profiles:
            raise SystemActionError("no known WiFi network")
        ssid = profiles[0].strip()
    result = _netsh("connect", f"name={ssid}")
    if result.returncode != 0:
        raise SystemActionError(result.stdout.strip() or "connection failed")
    return f"Connecting to {ssid}."

def wifi_status() -> str:
    output = _netsh("show", "interfaces").stdout
    state = re.search(r"^\s*State\s*:\s*(.+)$", output, re.MULTILINE)
    ssid = re.search(r"^\s*SSID\s*:\s*(.+)$", output, re.MULTILINE)
    state = state.group(1).strip() if state else "unknown"
    ssid = ssid.group(1).strip() if ssid else "unknown"
    if state.lower() == "connected":
        return f"WiFi connected to {ssid}."
    return f"WiFi not connected (state: {state})."

def now(timezone: str | None = None) -> datetime:
    if timezone:
        return datetime.now(ZoneInfo(timezone))
    return datetime.now().astimezone()

def take_screenshot(filename: str | None = None) -> str:
    if not _SCREENSHOT_OK:
        raise SystemActionError("screenshots are not available")
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    if not filename:
        filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
    if not filename.lower().endswith(".png"):
        filename += ".png"
    filepath = SCREENSHOTS_DIR / filename
    pyautogui.screenshot().save(str(filepath))
    log.info(f"[System] Screenshot saved: {filepath}")
    return str(filepath)

def set_pause(until: datetime, memory):
    memory.set_pause(until.isoformat())

def is_paused(memory) -> bool:
    paused_until = memory.get_pause()
    if not paused_until:
        return False
    try:
        target = datetime.fromisoformat(paused_until)
        current = datetime.now(target.tzinfo) if target.tzinfo else datetime.now()
        if current >= target:
            memory.clear_pause()
            log.info("[System] Pause expired, MARA is back.")
            return False
        return True
    except ValueError:
        memory.clear_pause()
        return False

def cancel_pause(memory):
    memory.clear_pause()

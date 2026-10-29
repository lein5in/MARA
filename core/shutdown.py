import atexit
import sys
import threading

from core.log import get_logger
log = get_logger(__name__)

_done = threading.Event()


def _step(name: str, fn):
    try:
        fn()
    except Exception as e:
        log.warning(f"[Shutdown] {name} failed: {e}")


def run():
    if _done.is_set():
        return
    _done.set()
    browser_mod = sys.modules.get("core.browser")
    if browser_mod is not None and browser_mod.browser.is_open:
        _step("browser close", browser_mod.browser.close)
        log.info("[Shutdown] Chrome closed.")
    listener_mod = sys.modules.get("core.listener")
    if listener_mod is not None:
        _step("microphone close", listener_mod.close)
    voice_mod = sys.modules.get("core.voice")
    if voice_mod is not None:
        _step("audio close", voice_mod.close_audio)


atexit.register(run)

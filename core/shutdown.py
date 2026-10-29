import atexit
import threading

from core.log import get_logger
log = get_logger(__name__)

_done = threading.Event()


def run():
    if _done.is_set():
        return
    _done.set()
    try:
        import sys
        browser_mod = sys.modules.get("core.browser")
        if browser_mod is not None and browser_mod.browser.is_open:
            browser_mod.browser.close()
            log.info("[Shutdown] Chrome closed.")
    except Exception as e:
        log.warning(f"[Shutdown] browser close failed: {e}")


atexit.register(run)

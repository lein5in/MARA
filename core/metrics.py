import threading
import time
from collections import deque

from core.log import get_logger
log = get_logger(__name__)

STEPS = ("released", "whisper_done", "first_token", "first_audio", "done")
RECAPS: deque = deque(maxlen=50)

_lock = threading.Lock()
_current: dict | None = None


def start(source: str, at: float | None = None):
    global _current
    with _lock:
        _current = {"source": source, "t0": at if at is not None else time.perf_counter(), "marks": {}}
        if source == "voice":
            _current["marks"]["released"] = _current["t0"]


def mark(step: str, at: float | None = None):
    with _lock:
        if _current is not None and step not in _current["marks"]:
            _current["marks"][step] = at if at is not None else time.perf_counter()


def active() -> bool:
    with _lock:
        return _current is not None


def discard():
    global _current
    with _lock:
        _current = None


def finish() -> dict | None:
    global _current
    with _lock:
        cur, _current = _current, None
    if cur is None:
        return None
    marks = cur["marks"]
    marks.setdefault("done", time.perf_counter())
    recap = {"source": cur["source"]}
    for step in STEPS:
        if step in marks:
            recap[step] = round(marks[step] - cur["t0"], 3)
    RECAPS.append(recap)
    log.info(format_recap(recap))
    return recap


def format_recap(recap: dict) -> str:
    parts = [f"{step}=+{recap[step]:.2f}s" for step in STEPS if step in recap and step != "released"]
    return f"[Latency] {recap['source']}: " + " ".join(parts)

import difflib
import json
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet

from core.config import USER_NAME, MEMORY_PATH, MEMORY_CAPS
from core.storage import atomic_write_bytes
from core.log import get_logger
log = get_logger(__name__)

SECTIONS = ("facts", "preferences", "context")
SIMILARITY = 0.85

TRIVIAL = {
    "ok", "okay", "yes", "no", "thanks", "thank", "you", "merci", "oui", "non", "cool", "super", "nice", "great",
    "d'accord", "dacord", "parfait", "so", "much", "very", "a", "lot", "beaucoup", "tres", "très", "bien", "good", "hi", "hello", "salut", "bonjour", "bye", "stop", "شكرا", "نعم", "لا",
}
SECRET_WORDS = re.compile(r"password|passcode|mot de passe|mdp|pin code|code pin|كلمة المرور|secret|token|api key", re.I)


def worth_extracting(text: str) -> bool:
    words = re.findall(r"[\w'’]+", (text or "").lower())
    if len(words) < 4:
        return False
    if all(w in TRIVIAL for w in words):
        return False
    if SECRET_WORDS.search(text):
        return False
    return True


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _default_memory() -> dict:
    return {"user": {"name": USER_NAME, "facts": [], "preferences": []}, "context": [],
            "paused_until": None, "last_updated": None}


def _normalize(entry) -> dict:
    if isinstance(entry, dict):
        return {"text": str(entry.get("text", "")).strip(), "added": entry.get("added") or _now()}
    return {"text": str(entry).strip(), "added": None}


def _similar(a: str, b: str) -> bool:
    a, b = a.lower().strip(" ."), b.lower().strip(" .")
    if not a or not b:
        return False
    shorter = a if len(a) <= len(b) else b
    if a == b or (len(shorter.split()) >= 3 and (a in b or b in a)):
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= SIMILARITY


class MemoryStore:
    def __init__(self, path: Path, fernet: Fernet, caps: dict | None = None):
        self._path = Path(path)
        self._fernet = fernet
        self._caps = caps or MEMORY_CAPS
        self._lock = threading.RLock()
        self._data = self._load()

    def _bucket(self, section: str) -> list:
        return self._data["context"] if section == "context" else self._data["user"][section]

    def _load(self) -> dict:
        if not self._path.exists():
            return _default_memory()
        try:
            data = json.loads(self._fernet.decrypt(self._path.read_bytes()).decode("utf-8"))
        except Exception as e:
            backup = self._path.with_name(f"{self._path.name}.{datetime.now().strftime('%Y%m%d_%H%M%S')}.corrupt")
            try:
                shutil.copy2(self._path, backup)
                log.error(f"[Memory] Could not read memory ({type(e).__name__}); copied it to {backup.name} "
                          f"and started with an empty memory.")
            except OSError as copy_error:
                log.error(f"[Memory] Could not read memory and could not back it up: {copy_error}")
            return _default_memory()
        base = _default_memory()
        base.update({k: v for k, v in data.items() if k != "user"})
        base["user"].update(data.get("user", {}))
        for section in SECTIONS:
            bucket = base["context"] if section == "context" else base["user"][section]
            bucket[:] = [e for e in (_normalize(x) for x in bucket or []) if e["text"]]
        return base

    def _save(self):
        with self._lock:
            self._data["last_updated"] = _now()
            raw = json.dumps(self._data, ensure_ascii=False, indent=2).encode("utf-8")
            try:
                atomic_write_bytes(self._path, self._fernet.encrypt(raw))
            except OSError as e:
                log.error(f"[Memory] Save failed, keeping changes in memory only: {e}")

    def _add(self, section: str, text: str):
        text = (text or "").strip()
        if not text:
            return
        with self._lock:
            bucket = self._bucket(section)
            for entry in bucket:
                if _similar(entry["text"], text):
                    bucket.remove(entry)
                    break
            bucket.append({"text": text, "added": _now()})
            cap = self._caps.get(section, 50)
            if len(bucket) > cap:
                del bucket[:len(bucket) - cap]
            self._save()

    def add_fact(self, fact: str):
        self._add("facts", fact)

    def add_preference(self, preference: str):
        self._add("preferences", preference)

    def add_context(self, info: str):
        self._add("context", info)

    def items(self) -> dict[str, list[str]]:
        with self._lock:
            return {s: [e["text"] for e in self._bucket(s)] for s in SECTIONS}

    def entries(self, section: str) -> list[dict]:
        with self._lock:
            return [dict(e) for e in self._bucket(section)]

    def remove_last_fact(self):
        with self._lock:
            facts = self._bucket("facts")
            if not facts:
                return None
            removed = facts.pop()["text"]
            self._save()
            return removed

    def remove_matching(self, text: str) -> list[str]:
        needle = (text or "").lower().strip()
        removed = []
        if not needle:
            return removed
        with self._lock:
            for section in SECTIONS:
                bucket = self._bucket(section)
                for entry in list(bucket):
                    if needle in entry["text"].lower():
                        bucket.remove(entry)
                        removed.append(entry["text"])
            if removed:
                self._save()
        return removed

    def clear(self):
        with self._lock:
            pause = self._data.get("paused_until")
            self._data = _default_memory()
            self._data["paused_until"] = pause
            self._save()
        log.info("[Memory] Cleared.")

    def set_pause(self, until_iso: str):
        with self._lock:
            self._data["paused_until"] = until_iso
            self._save()
        log.info(f"[System] Paused until {until_iso}")

    def get_pause(self) -> str | None:
        return self._data.get("paused_until")

    def clear_pause(self):
        with self._lock:
            self._data["paused_until"] = None
            self._save()
        log.info("[System] Pause cancelled.")

    def get_context_for_prompt(self) -> str:
        items = self.items()
        if not any(items.values()):
            return ""
        parts = []
        if items["facts"]:
            parts.append("things you already know about them: " + "; ".join(items["facts"]))
        if items["preferences"]:
            parts.append("their habits and preferences: " + "; ".join(items["preferences"]))
        if items["context"]:
            parts.append("what's currently going on for them: " + "; ".join(items["context"]))
        return (
            "Background on the user, for your own awareness only "
            "(never list, recite, or announce this; only let it surface naturally, "
            "and only if directly relevant to their current message): "
            + ". ".join(parts)
        )


class Memory(MemoryStore):
    _instance = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        with cls._instance_lock:
            if cls._instance is None:
                from memory.keystore import get_key
                instance = super().__new__(cls)
                MemoryStore.__init__(instance, MEMORY_PATH, Fernet(get_key()))
                cls._instance = instance
        return cls._instance

    def __init__(self):
        pass

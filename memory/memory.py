import os
import json
from datetime import datetime
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "mara_memory.enc")
KEY_FILE    = os.path.join(os.path.dirname(__file__), "mara.key")

def _load_or_create_key() -> Fernet:
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            key = f.read()
    else:
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        print("Nouvelle clé mémoire générée.")
    return Fernet(key)

_fernet = _load_or_create_key()

def _default_memory() -> dict:
    return {
        "user": {
            "name":        os.getenv("USER_NAME", ""),
            "facts":       [],
            "preferences": [],
        },
        "context":      [],
        "paused_until": None,
        "last_updated": None
    }

_instance = None

class Memory:
    def __new__(cls):
        global _instance
        if _instance is None:
            _instance = super().__new__(cls)
            _instance._data = _instance._load()
        return _instance

    def _load(self) -> dict:
        if not os.path.exists(MEMORY_FILE):
            return _default_memory()
        try:
            with open(MEMORY_FILE, "rb") as f:
                decrypted = _fernet.decrypt(f.read())
            data = json.loads(decrypted.decode("utf-8"))
            if "paused_until" not in data:
                data["paused_until"] = None
            return data
        except Exception as e:
            print(f"Erreur lecture mémoire : {e} — mémoire réinitialisée.")
            return _default_memory()

    def _save(self):
        self._data["last_updated"] = datetime.now().isoformat()
        raw = json.dumps(self._data, ensure_ascii=False, indent=2).encode("utf-8")
        encrypted = _fernet.encrypt(raw)
        with open(MEMORY_FILE, "wb") as f:
            f.write(encrypted)

    def add_fact(self, fact: str):
        fact = fact.strip()
        if fact and fact not in self._data["user"]["facts"]:
            self._data["user"]["facts"].append(fact)
            self._save()

    def add_preference(self, preference: str):
        preference = preference.strip()
        if preference and preference not in self._data["user"]["preferences"]:
            self._data["user"]["preferences"].append(preference)
            self._save()

    def add_context(self, info: str):
        info = info.strip()
        if info and info not in self._data["context"]:
            self._data["context"].append(info)
            self._save()

    def remove_last_fact(self):
        if self._data["user"]["facts"]:
            removed = self._data["user"]["facts"].pop()
            self._save()
            return removed
        return None

    def clear(self):
        pause = self._data.get("paused_until")
        self._data = _default_memory()
        self._data["paused_until"] = pause
        self._save()
        print("Mémoire effacée.")

    def set_pause(self, until_iso: str):
        self._data["paused_until"] = until_iso
        self._save()
        print(f"[System] MARA en pause jusqu'à : {until_iso}")

    def get_pause(self) -> str | None:
        return self._data.get("paused_until")

    def clear_pause(self):
        self._data["paused_until"] = None
        self._save()
        print("[System] Pause annulée.")

    def get_summary(self) -> str:
        facts = self._data["user"]["facts"]
        prefs = self._data["user"]["preferences"]
        ctx   = self._data["context"]

        parts = []
        if facts:
            parts.append("Ce que je sais sur toi : " + ", ".join(facts))
        if prefs:
            parts.append("Tes préférences : " + ", ".join(prefs))
        if ctx:
            parts.append("Contexte actuel : " + ", ".join(ctx))

        return ". ".join(parts) if parts else "Je n'ai encore rien mémorisé sur toi."

    def get_context_for_prompt(self) -> str:
        facts = self._data["user"]["facts"]
        prefs = self._data["user"]["preferences"]
        ctx   = self._data["context"]

        if not facts and not prefs and not ctx:
            return ""

        parts = []
        if facts:
            parts.append("things you already know about them: " + "; ".join(facts))
        if prefs:
            parts.append("their habits and preferences: " + "; ".join(prefs))
        if ctx:
            parts.append("what's currently going on for them: " + "; ".join(ctx))

        memory_text = ". ".join(parts)

        return (
            "Background on the user, for your own awareness only "
            "(never list, recite, or announce this — only let it surface naturally, "
            "and only if directly relevant to their current message): "
            + memory_text
        )

    def debug(self):
        print(json.dumps(self._data, ensure_ascii=False, indent=2))
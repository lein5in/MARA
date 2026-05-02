import os
import json
from datetime import datetime
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "mara_memory.enc")
KEY_FILE    = os.path.join(os.path.dirname(__file__), "mara.key")

# ─── Clé de chiffrement ───────────────────────────────────────────────────────

def _load_or_create_key() -> Fernet:
    """Charge la clé Fernet existante ou en génère une nouvelle."""
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

# ─── Structure par défaut ─────────────────────────────────────────────────────

def _default_memory() -> dict:
    return {
        "user": {
            "name":        os.getenv("USER_NAME", ""),
            "facts":       [],   # ["préfère le café noir", "étudiant en génie", ...]
            "preferences": [],   # ["répond court", "langue FR le soir", ...]
        },
        "context":      [],      # infos temporaires / projets en cours
        "paused_until": None,    # ISO timestamp — MARA en pause jusqu'à cette date
        "last_updated": None
    }

# ─── Classe Memory ────────────────────────────────────────────────────────────

class Memory:
    def __init__(self):
        self._data = self._load()

    # ── I/O chiffré ──────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if not os.path.exists(MEMORY_FILE):
            return _default_memory()
        try:
            with open(MEMORY_FILE, "rb") as f:
                decrypted = _fernet.decrypt(f.read())
            data = json.loads(decrypted.decode("utf-8"))
            # Migration : anciens fichiers sans paused_until
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

    # ── Mémoire utilisateur ───────────────────────────────────────────────────

    def add_fact(self, fact: str):
        """Ajoute un fait sur l'utilisateur (ex: 'a un exam lundi')."""
        fact = fact.strip()
        if fact and fact not in self._data["user"]["facts"]:
            self._data["user"]["facts"].append(fact)
            self._save()

    def add_preference(self, preference: str):
        """Ajoute une préférence (ex: 'préfère les réponses courtes')."""
        preference = preference.strip()
        if preference and preference not in self._data["user"]["preferences"]:
            self._data["user"]["preferences"].append(preference)
            self._save()

    def add_context(self, info: str):
        """Ajoute une info de contexte temporaire (projet en cours, etc.)."""
        info = info.strip()
        if info and info not in self._data["context"]:
            self._data["context"].append(info)
            self._save()

    def remove_last_fact(self):
        """Supprime le dernier fait ajouté."""
        if self._data["user"]["facts"]:
            removed = self._data["user"]["facts"].pop()
            self._save()
            return removed
        return None

    def clear(self):
        """Efface toute la mémoire utilisateur et repart de zéro (conserve paused_until)."""
        pause = self._data.get("paused_until")  # on ne réinitialise pas la pause
        self._data = _default_memory()
        self._data["paused_until"] = pause
        self._save()
        print("Mémoire effacée.")

    # ── Auto-contrôle ─────────────────────────────────────────────────────────

    def set_pause(self, until_iso: str):
        """
        Met MARA en pause jusqu'au timestamp ISO fourni.
        Ex: until_iso = "2025-12-01T09:00:00"
        """
        self._data["paused_until"] = until_iso
        self._save()
        print(f"[System] MARA en pause jusqu'à : {until_iso}")

    def get_pause(self) -> str | None:
        """Retourne le timestamp ISO de fin de pause, ou None si pas en pause."""
        return self._data.get("paused_until")

    def clear_pause(self):
        """Annule la pause — réveil immédiat."""
        self._data["paused_until"] = None
        self._save()
        print("[System] Pause annulée.")

    # ── Prompt & affichage ────────────────────────────────────────────────────

    def get_summary(self) -> str:
        """Retourne un résumé lisible pour l'affichage vocal."""
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
        """
        Retourne un bloc de contexte à injecter dans le system prompt de Claude.
        Retourne une chaîne vide si la mémoire est vide.
        """
        facts = self._data["user"]["facts"]
        prefs = self._data["user"]["preferences"]
        ctx   = self._data["context"]

        if not facts and not prefs and not ctx:
            return ""

        lines = ["MÉMOIRE LONG TERME — ce que tu sais sur l'utilisateur :"]
        if facts:
            lines.append("Faits : " + " | ".join(facts))
        if prefs:
            lines.append("Préférences : " + " | ".join(prefs))
        if ctx:
            lines.append("Contexte en cours : " + " | ".join(ctx))

        return "\n".join(lines)

    def debug(self):
        """Affiche la mémoire en clair dans le terminal (debug uniquement)."""
        print(json.dumps(self._data, ensure_ascii=False, indent=2))
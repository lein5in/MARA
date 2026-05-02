import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# ─── Imports optionnels — pas de crash si lib absente ────────────────────────
try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    from ctypes import cast, POINTER
    _PYCAW_OK = True
except ImportError:
    _PYCAW_OK = False
    print("[System] pycaw non disponible — contrôle volume désactivé.")

try:
    import screen_brightness_control as sbc
    _SBC_OK = True
except ImportError:
    _SBC_OK = False
    print("[System] screen_brightness_control non disponible — contrôle luminosité désactivé.")

try:
    import pyautogui
    from PIL import Image
    _SCREENSHOT_OK = True
except ImportError:
    _SCREENSHOT_OK = False
    print("[System] pyautogui/PIL non disponible — screenshots désactivés.")

# ─── Dossier screenshots — Pictures\Screenshots comme le reste de Windows ─────
SCREENSHOTS_DIR = Path.home() / "Pictures" / "Screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# ─── Conversion mots → chiffres (FR + EN) ────────────────────────────────────
_WORD_TO_NUM = {
    # EN
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
    "thirty": 30, "forty": 40, "sixty": 60,
    # FR
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
    "quinze": 15, "vingt": 20, "trente": 30, "quarante": 40, "soixante": 60,
}

def _normalize_numbers(text: str) -> str:
    """Remplace les nombres en lettres par leurs équivalents numériques."""
    for word, num in _WORD_TO_NUM.items():
        text = re.sub(rf"\b{word}\b", str(num), text, flags=re.IGNORECASE)
    return text


# ══════════════════════════════════════════════════════════════════════════════
# VOLUME
# ══════════════════════════════════════════════════════════════════════════════

_volume_interface = None  # Singleton — créé une fois, réutilisé

def _get_volume_interface():
    """
    Retourne l'interface pycaw IAudioEndpointVolume.
    Singleton — évite les fuites COM et le VTable error à chaque appel.
    """
    global _volume_interface
    if not _PYCAW_OK:
        return None
    if _volume_interface is not None:
        return _volume_interface
    try:
        import comtypes
        comtypes.CoInitialize()
        devices = AudioUtilities.GetSpeakers()
        interface = devices._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        _volume_interface = cast(interface, POINTER(IAudioEndpointVolume))
        return _volume_interface
    except Exception as e:
        print(f"[System] Erreur interface volume : {e}")
        return None


def set_volume(level: int) -> str:
    """Règle le volume système entre 0 et 100."""
    level = max(0, min(100, level))
    vol = _get_volume_interface()
    if not vol:
        return "Contrôle volume non disponible."
    try:
        vol.SetMasterVolumeLevelScalar(level / 100.0, None)
        return f"Volume réglé à {level}%."
    except Exception as e:
        return f"Erreur volume : {e}"


def get_volume() -> str:
    """Retourne le niveau de volume actuel en pourcentage."""
    vol = _get_volume_interface()
    if not vol:
        return "Contrôle volume non disponible."
    try:
        level = round(vol.GetMasterVolumeLevelScalar() * 100)
        muted = vol.GetMute()
        status = " (muet)" if muted else ""
        return f"Volume actuel : {level}%{status}."
    except Exception as e:
        return f"Erreur lecture volume : {e}"


def mute() -> str:
    """Coupe le son."""
    vol = _get_volume_interface()
    if not vol:
        return "Contrôle volume non disponible."
    try:
        vol.SetMute(1, None)
        return "Son coupé."
    except Exception as e:
        return f"Erreur mute : {e}"


def unmute() -> str:
    """Réactive le son."""
    vol = _get_volume_interface()
    if not vol:
        return "Contrôle volume non disponible."
    try:
        vol.SetMute(0, None)
        return "Son réactivé."
    except Exception as e:
        return f"Erreur unmute : {e}"


# ══════════════════════════════════════════════════════════════════════════════
# LUMINOSITÉ
# ══════════════════════════════════════════════════════════════════════════════

def set_brightness(level: int) -> str:
    """Règle la luminosité de l'écran entre 0 et 100."""
    if not _SBC_OK:
        return "Contrôle luminosité non disponible."
    level = max(0, min(100, level))
    try:
        sbc.set_brightness(level)
        return f"Luminosité réglée à {level}%."
    except Exception as e:
        return f"Erreur luminosité : {e}"


def get_brightness() -> str:
    """Retourne la luminosité actuelle."""
    if not _SBC_OK:
        return "Contrôle luminosité non disponible."
    try:
        level = sbc.get_brightness()
        if isinstance(level, list):
            level = level[0]
        return f"Luminosité actuelle : {level}%."
    except Exception as e:
        return f"Erreur lecture luminosité : {e}"


# ══════════════════════════════════════════════════════════════════════════════
# WIFI
# ══════════════════════════════════════════════════════════════════════════════

def wifi_disconnect() -> str:
    """Déconnecte le WiFi."""
    try:
        subprocess.run(
            ["netsh", "wlan", "disconnect"],
            capture_output=True, text=True, check=True
        )
        return "WiFi déconnecté."
    except subprocess.CalledProcessError as e:
        return f"Erreur déconnexion WiFi : {e.stderr.strip()}"


def wifi_connect(ssid: str | None = None) -> str:
    """Reconnecte au dernier réseau connu, ou à un SSID spécifique."""
    try:
        if ssid:
            result = subprocess.run(
                ["netsh", "wlan", "connect", f"name={ssid}"],
                capture_output=True, text=True
            )
        else:
            profiles_result = subprocess.run(
                ["netsh", "wlan", "show", "profiles"],
                capture_output=True, text=True
            )
            profiles = re.findall(r"All User Profile\s*:\s*(.+)", profiles_result.stdout)
            if not profiles:
                return "Aucun réseau WiFi connu trouvé."
            ssid = profiles[0].strip()
            result = subprocess.run(
                ["netsh", "wlan", "connect", f"name={ssid}"],
                capture_output=True, text=True
            )

        if "successfully" in result.stdout.lower() or result.returncode == 0:
            return f"Connexion à {ssid} initiée."
        return f"Échec connexion WiFi : {result.stdout.strip()}"

    except Exception as e:
        return f"Erreur WiFi : {e}"


def get_wifi_status() -> str:
    """Retourne le statut WiFi actuel."""
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True
        )
        output = result.stdout

        state_match = re.search(r"State\s*:\s*(.+)", output)
        ssid_match  = re.search(r"SSID\s*:\s*(.+)", output)

        state = state_match.group(1).strip() if state_match else "inconnu"
        ssid  = ssid_match.group(1).strip()  if ssid_match  else "inconnu"

        if "connected" in state.lower():
            return f"WiFi connecté à {ssid}."
        return f"WiFi déconnecté (dernier réseau : {ssid})."

    except Exception as e:
        return f"Erreur lecture WiFi : {e}"


# ══════════════════════════════════════════════════════════════════════════════
# SCREENSHOTS
# ══════════════════════════════════════════════════════════════════════════════

def take_screenshot(filename: str | None = None) -> str:
    """
    Prend un screenshot et le sauvegarde dans Pictures\Screenshots.
    Retourne le chemin du fichier sauvegardé.
    """
    if not _SCREENSHOT_OK:
        return "Screenshots non disponibles."
    try:
        if not filename:
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if not filename.endswith(".png"):
            filename += ".png"

        filepath = SCREENSHOTS_DIR / filename
        screenshot = pyautogui.screenshot()
        screenshot.save(str(filepath))
        print(f"[System] Screenshot sauvegardé : {filepath}")
        return str(filepath)
    except Exception as e:
        return f"Erreur screenshot : {e}"


def take_screenshot_for_vision() -> str | None:
    """
    Prend un screenshot et retourne le chemin.
    Utilisé par brain.py pour la conscience d'écran.
    """
    if not _SCREENSHOT_OK:
        return None
    try:
        filename = f"vision_{datetime.now().strftime('%Y%m%d_%H%M%S%f')}.png"
        filepath = SCREENSHOTS_DIR / filename
        screenshot = pyautogui.screenshot()
        screenshot.save(str(filepath))
        return str(filepath)
    except Exception as e:
        print(f"[System] Erreur screenshot vision : {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# AUTO-CONTRÔLE
# ══════════════════════════════════════════════════════════════════════════════

_DURATION_PATTERNS = [
    (r"(\d+)\s*h(?:ours?|eures?)?",                                              "hours"),
    (r"(\d+)\s*m(?:in(?:utes?)?)?",                                              "minutes"),
    (r"(\d+)\s*(?:days?|jours?)",                                                "days"),
    (r"(?:until|jusqu['\u2019]?à?)\s*(\d{1,2})h?(?::(\d{2}))?(?:\s*(am|pm))?", "until_time"),
]


def parse_pause_duration(text: str) -> datetime | None:
    """
    Parse une durée ou heure cible depuis le texte et retourne un datetime.
    Supporte les nombres en lettres (one, deux, three...) en FR et EN.
    """
    text = _normalize_numbers(text.lower().strip())
    now  = datetime.now()

    for pattern, unit in _DURATION_PATTERNS:
        match = re.search(pattern, text)
        if not match:
            continue

        if unit == "hours":
            return now + timedelta(hours=int(match.group(1)))

        elif unit == "minutes":
            return now + timedelta(minutes=int(match.group(1)))

        elif unit == "days":
            return now + timedelta(days=int(match.group(1)))

        elif unit == "until_time":
            hour   = int(match.group(1))
            minute = int(match.group(2)) if match.group(2) else 0
            period = match.group(3)

            if period == "pm" and hour != 12:
                hour += 12
            elif period == "am" and hour == 12:
                hour = 0

            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            return target

    return None


def set_pause(duration_text: str, memory) -> str:
    """Met MARA en pause en parsant le texte de durée."""
    target = parse_pause_duration(duration_text)
    if not target:
        return "Je n'ai pas compris la durée. Dis par exemple 'pour 2 heures' ou 'jusqu'à 21h'."

    memory.set_pause(target.isoformat())

    delta = target - datetime.now()
    total_minutes = round(delta.total_seconds() / 60)
    if total_minutes >= 60:
        hours   = total_minutes // 60
        minutes = total_minutes % 60
        duration_str = f"{hours}h{minutes:02d}" if minutes else f"{hours} heure{'s' if hours > 1 else ''}"
    else:
        duration_str = f"{total_minutes} minute{'s' if total_minutes > 1 else ''}"

    return f"Je me désactive pour {duration_str}. Réveil à {target.strftime('%H:%M')}."


def is_paused(memory) -> bool:
    """
    Vérifie si MARA est en pause.
    Nettoie automatiquement le flag si la pause est expirée.
    """
    paused_until = memory.get_pause()
    if not paused_until:
        return False

    try:
        target = datetime.fromisoformat(paused_until)
        if datetime.now() >= target:
            memory.clear_pause()
            print("[System] Pause expirée — MARA réactivée.")
            return False
        return True
    except ValueError:
        memory.clear_pause()
        return False


def cancel_pause(memory) -> str:
    """Annule la pause en cours — réveil immédiat."""
    memory.clear_pause()
    return "Je suis de retour."
import os
import re
import subprocess
import pyautogui
import psutil
from pathlib import Path
from core.app_registry import get_registry, find_app
from core.browser import browser
from core import system
from memory.memory import Memory

# ─── Registre apps — chargé une seule fois au démarrage ──────────────────────
_registry = get_registry()

# ─── Mémoire — partagée avec brain.py via le même fichier chiffré ─────────────
_memory = Memory()

# ─── Actions sensibles qui nécessitent une confirmation ───────────────────────
PROTOCOL_APPS = {
    "ms-windows-store":     "ms-windows-store:",
    "ms-windows-store:":    "ms-windows-store:",
    "microsoft store":      "ms-windows-store:",
    "store":                "ms-windows-store:",
    "windows store":        "ms-windows-store:",
    "settings":             "ms-settings:",
    "ms-settings":          "ms-settings:",
    "windows settings":     "ms-settings:",
    "xbox":                 "xbox:",
    "calculator":           "calculator:",
    "mail":                 "outlookmail:",
    "calendar":             "outlookcal:",
    "maps":                 "bingmaps:",
    "clock":                "ms-clock:",
    "alarms":               "ms-clock:",
}

SENSITIVE_ACTIONS = {"delete", "shutdown", "restart", "format", "browser_delete_credentials"}

# ─── Executor principal ───────────────────────────────────────────────────────

def execute(actions: list) -> list[str]:
    """
    Reçoit une liste d'actions JSON de Claude et les exécute.
    Retourne une liste de résultats pour chaque action.
    """
    results = []
    for action in actions:
        action_type = action.get("type", "").lower()
        try:
            # ── Apps & fichiers ───────────────────────────────────────────────
            if action_type == "run":
                result = _run(action)
            elif action_type == "open":
                result = _open(action)
            elif action_type == "type":
                result = _type(action)
            elif action_type == "hotkey":
                result = _hotkey(action)
            elif action_type == "kill":
                result = _kill(action)
            elif action_type == "search":
                result = _search(action)
            elif action_type == "open_with":
                result = _open_with(action)
            # ── Volume ────────────────────────────────────────────────────────
            elif action_type == "set_volume":
                result = system.set_volume(action.get("level", 50))
            elif action_type == "get_volume":
                result = system.get_volume()
            elif action_type == "mute":
                result = system.mute()
            elif action_type == "unmute":
                result = system.unmute()
            # ── Luminosité ────────────────────────────────────────────────────
            elif action_type == "set_brightness":
                result = system.set_brightness(action.get("level", 80))
            elif action_type == "get_brightness":
                result = system.get_brightness()
            # ── WiFi ──────────────────────────────────────────────────────────
            elif action_type == "wifi_connect":
                result = system.wifi_connect(action.get("ssid"))
            elif action_type == "wifi_disconnect":
                result = system.wifi_disconnect()
            elif action_type == "wifi_status":
                result = system.get_wifi_status()
            # ── Screenshots ───────────────────────────────────────────────────
            elif action_type == "screenshot":
                result = system.take_screenshot(action.get("filename"))
            # ── Auto-contrôle ─────────────────────────────────────────────────
            elif action_type == "pause":
                result = system.set_pause(action.get("duration", ""), _memory)
            elif action_type == "cancel_pause":
                result = system.cancel_pause(_memory)
            # ── Browser ───────────────────────────────────────────────────────
            elif action_type == "browser_navigate":
                result = _browser_navigate(action)
            elif action_type == "browser_click":
                result = _browser_click(action)
            elif action_type == "browser_type":
                result = _browser_type(action)
            elif action_type == "browser_login":
                result = _browser_login(action)
            elif action_type == "browser_save_credentials":
                result = _browser_save_credentials(action)
            elif action_type == "browser_delete_credentials":
                result = _browser_delete_credentials(action)
            elif action_type == "browser_wait":
                result = _browser_wait(action)
            elif action_type == "browser_read":
                result = _browser_read(action)
            elif action_type == "browser_close":
                result = _browser_close(action)
            else:
                result = f"Action inconnue : {action_type}"
        except Exception as e:
            result = f"Erreur sur {action_type} : {e}"

        results.append(result)
        print(f"[Executor] {action_type} → {result}")

    return results


# ─── Primitives système ───────────────────────────────────────────────────────

def _run(action: dict) -> str:
    """
    Lance une app en cherchant d'abord dans le registre dynamique,
    puis protocoles Windows, puis PATH en fallback.
    """
    command = action.get("command", "")
    if not command:
        return "Commande vide."

    command = os.path.expandvars(command)
    parts = command.split()
    app_name = parts[0].lower()
    args = parts[1:] if len(parts) > 1 else []

    # 0. Protocoles connus — vérifié en premier, peu importe la formulation
    full_name = command.lower().strip()
    protocol = PROTOCOL_APPS.get(app_name) or PROTOCOL_APPS.get(full_name)
    if protocol:
        subprocess.Popen(
            f'start "" "{protocol}"',
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return f"Lancé : {protocol}"

    # 1. Cherche dans le registre dynamique
    found_path = find_app(app_name, _registry)
    if found_path and Path(found_path).exists():
        subprocess.Popen(
            [found_path] + args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return f"Lancé : {Path(found_path).name}"

    # 2. Protocoles Windows (ms-windows-store:, etc.)
    if ":" in app_name and "/" not in app_name and "\\" not in app_name:
        subprocess.Popen(
            f'start "" {command}',
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return f"Lancé : {command}"

    # 3. Fallback PATH
    subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return f"Lancé : {command}"


def _open(action: dict) -> str:
    """Ouvre un fichier, dossier, ou URL avec l'application par défaut."""
    path = action.get("path", "")
    if not path:
        return "Chemin vide."

    if path.startswith("http://") or path.startswith("https://"):
        subprocess.Popen(
            f'start "" "{path}"',
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return f"URL ouverte : {path}"

    path = os.path.expandvars(path)
    resolved = Path(path).expanduser().resolve()

    if not resolved.exists():
        home = Path.home()
        fallback = home / Path(path).name
        if fallback.exists():
            resolved = fallback
        else:
            return f"Chemin introuvable : {path}"

    os.startfile(str(resolved))
    return f"Ouvert : {resolved}"


def _type(action: dict) -> str:
    """Tape du texte via pyautogui dans la fenêtre active."""
    text = action.get("text", "")
    if not text:
        return "Texte vide."
    pyautogui.typewrite(text, interval=0.03)
    return f"Texte tapé : {text[:30]}..."


def _hotkey(action: dict) -> str:
    """Exécute un raccourci clavier."""
    keys = action.get("keys", [])
    if not keys:
        return "Touches vides."
    pyautogui.hotkey(*keys)
    return f"Raccourci : {'+'.join(keys)}"


def _kill(action: dict) -> str:
    """Ferme une application par nom de processus."""
    process_name = action.get("process", "").lower()
    if not process_name:
        return "Nom de processus vide."

    killed = False
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] and proc.info['name'].lower() == process_name:
            proc.terminate()
            killed = True

    return f"Fermé : {process_name}" if killed else f"Processus introuvable : {process_name}"


def _search(action: dict) -> str:
    """Cherche un fichier ou dossier par nom et l'ouvre."""
    name = action.get("name", "").lower()
    folder = action.get("folder", "%USERPROFILE%")
    is_folder = action.get("is_folder", False)

    if not name:
        return "Nom vide."

    path = _find_file(name, folder, find_folder=is_folder)
    if not path:
        return f"Aucun résultat pour : {name}"

    os.startfile(str(path))
    return f"Ouvert : {path.name}"


def _open_with(action: dict) -> str:
    """Cherche un fichier/dossier et l'ouvre avec une app spécifique."""
    name = action.get("name", "").lower()
    app = action.get("app", "").lower()
    folder = action.get("folder", "%USERPROFILE%")
    is_folder = action.get("is_folder", False)

    if not name or not app:
        return "Nom ou app manquant."

    target = _find_file(name, folder, find_folder=is_folder)
    if not target:
        return f"Introuvable : {name}"

    app_path = find_app(app, _registry)
    if not app_path or not Path(app_path).exists():
        app_path = app

    subprocess.Popen(
        [app_path, str(target)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return f"Ouvert : {target.name} dans {Path(app_path).stem if app_path != app else app}"


# ─── Primitives browser ───────────────────────────────────────────────────────

def _browser_navigate(action: dict) -> str:
    url = action.get("url", "")
    if not url:
        return "URL vide."
    return browser.navigate(url)


def _browser_click(action: dict) -> str:
    selector = action.get("selector", "")
    by = action.get("by", "css")
    timeout = action.get("timeout", 10)
    if not selector:
        return "Sélecteur vide."
    return browser.click(selector, by=by, timeout=timeout)


def _browser_type(action: dict) -> str:
    selector = action.get("selector", "")
    text = action.get("text", "")
    by = action.get("by", "css")
    if not selector or not text:
        return "Sélecteur ou texte manquant."
    return browser.type_text(selector, text, by=by)


def _browser_login(action: dict) -> str:
    site = action.get("site", "")
    if not site:
        return "Site manquant."
    return browser.login(site)


def _browser_save_credentials(action: dict) -> str:
    site = action.get("site", "")
    email = action.get("email", "")
    password = action.get("password", "")
    if not site or not email or not password:
        return "Site, email ou mot de passe manquant."
    return browser.save_credential(site, email, password)


def _browser_delete_credentials(action: dict) -> str:
    site = action.get("site", "")
    if not site:
        return "Site manquant."
    return browser.delete_credential(site)


def _browser_wait(action: dict) -> str:
    selector = action.get("selector", "")
    by = action.get("by", "css")
    timeout = action.get("timeout", 10)
    if not selector:
        return "Sélecteur vide."
    return browser.wait_for(selector, by=by, timeout=timeout)


def _browser_read(action: dict) -> str:
    selector = action.get("selector", "")
    by = action.get("by", "css")
    if not selector:
        return browser.read_page()
    return browser.read_element(selector, by=by)


def _browser_close(action: dict) -> str:
    return browser.close()


# ─── Utilitaire fichiers ──────────────────────────────────────────────────────

def _find_file(name: str, folder: str, find_folder: bool = False) -> Path | None:
    """Cherche un fichier ou dossier par nom partiel."""
    name = name.lower()

    priority_folders = [
        Path.home() / "Documents",
        Path.home() / "Desktop",
        Path.home() / "Downloads",
        Path(os.path.expandvars(folder)).expanduser(),
    ]

    for search_path in priority_folders:
        if not search_path.exists():
            continue
        try:
            if find_folder:
                matches = [p for p in search_path.rglob(f"*{name}*") if p.is_dir()]
            else:
                matches = [p for p in search_path.rglob(f"*{name}*") if p.is_file() and p.suffix.lower() != ".lnk"]
            if matches:
                return matches[0]
        except PermissionError:
            continue

    home = Path.home()
    try:
        if find_folder:
            matches = [p for p in home.glob(f"**/*{name}*") if p.is_dir() and len(p.relative_to(home).parts) <= 3]
        else:
            matches = [p for p in home.glob(f"**/*{name}*") if p.is_file() and p.suffix.lower() != ".lnk" and len(p.relative_to(home).parts) <= 3]
        if matches:
            return matches[0]
    except PermissionError:
        pass

    return None


# ─── Utilitaires ─────────────────────────────────────────────────────────────

def needs_confirmation(actions: list) -> bool:
    """Retourne True si une des actions est sensible et nécessite confirmation."""
    for action in actions:
        if action.get("type", "").lower() in SENSITIVE_ACTIONS:
            return True
    return False


def list_running_apps() -> list[str]:
    """Retourne la liste des applications actuellement ouvertes."""
    apps = set()
    for proc in psutil.process_iter(['name']):
        name = proc.info.get('name', '')
        if name and name.endswith('.exe'):
            apps.add(name)
    return sorted(apps)
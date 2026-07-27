import os
import re
import subprocess
import time
import pyautogui
import psutil
from pathlib import Path
from core.app_registry import get_registry, find_app
from core.browser import browser
from core import system
from memory.memory import Memory

_registry = get_registry()

_memory = Memory()

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
    "cmd":              "cmd.exe",
    "command prompt":   "cmd.exe",
    "terminal":         "cmd.exe",
    "powershell":       "powershell.exe",
}

SENSITIVE_ACTIONS = {"delete", "shutdown", "restart", "format", "browser_delete_credentials"}

def execute(actions: list) -> list[str]:
    results = []
    for action in actions:
        action_type = action.get("type", "").lower()
        try:

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

            elif action_type == "set_volume":
                result = system.set_volume(action.get("level", 50))
            elif action_type == "get_volume":
                result = system.get_volume()
            elif action_type == "mute":
                result = system.mute()
            elif action_type == "unmute":
                result = system.unmute()

            elif action_type == "set_brightness":
                result = system.set_brightness(action.get("level", 80))
            elif action_type == "get_brightness":
                result = system.get_brightness()

            elif action_type == "wifi_connect":
                result = system.wifi_connect(action.get("ssid"))
            elif action_type == "wifi_disconnect":
                result = system.wifi_disconnect()
            elif action_type == "wifi_status":
                result = system.get_wifi_status()
            elif action_type == "get_time":
                result = system.get_time(action.get("timezone"))

            elif action_type == "screenshot":
                result = system.take_screenshot(action.get("filename"))

            elif action_type == "visual_render":
                result = action.get("html", "")

            elif action_type == "pause":
                result = system.set_pause(action.get("duration", ""), _memory)
            elif action_type == "cancel_pause":
                result = system.cancel_pause(_memory)

            elif action_type == "silent_on":
                result = system.enable_silent()
            elif action_type == "silent_off":
                result = system.disable_silent()

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

def _get_foreground_window():
    try:
        import win32gui
        return win32gui.GetForegroundWindow()
    except Exception:
        return None

def _wait_for_new_window(prev_hwnd, timeout=4.0):
    try:
        import win32gui
    except ImportError:
        return
    start = time.time()
    while time.time() - start < timeout:
        try:
            current = win32gui.GetForegroundWindow()
            if current != prev_hwnd and win32gui.GetWindowText(current):
                time.sleep(0.35)
                return
        except Exception:
            return
        time.sleep(0.15)

def _run(action: dict) -> str:
    command = action.get("command", "")
    if not command:
        return "Commande vide."

    command = os.path.expandvars(command)
    parts = command.split()
    app_name = parts[0].lower()
    args = parts[1:] if len(parts) > 1 else []

    prev_hwnd = _get_foreground_window()

    full_name = command.lower().strip()
    protocol = PROTOCOL_APPS.get(app_name) or PROTOCOL_APPS.get(full_name)
    if protocol:
        subprocess.Popen(
            f'start "" "{protocol}"',
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        _wait_for_new_window(prev_hwnd)
        return f"Lancé : {protocol}"

    found_path = find_app(app_name, _registry)
    if found_path and Path(found_path).exists():
        subprocess.Popen(
            [found_path] + args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        _wait_for_new_window(prev_hwnd)
        return f"Lancé : {Path(found_path).name}"

    if ":" in app_name and "/" not in app_name and "\\" not in app_name:
        subprocess.Popen(
            f'start "" {command}',
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        _wait_for_new_window(prev_hwnd)
        return f"Lancé : {command}"

    subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    _wait_for_new_window(prev_hwnd)
    return f"Lancé : {command}"

def _open(action: dict) -> str:
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
    text = action.get("text", "")
    if not text:
        return "Texte vide."
    import pyperclip
    previous = None
    try:
        previous = pyperclip.paste()
    except Exception:
        pass
    pyperclip.copy(text)
    time.sleep(0.15)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.1)
    if previous is not None:
        try:
            pyperclip.copy(previous)
        except Exception:
            pass
    return f"Texte tapé : {text[:30]}..."

def _hotkey(action: dict) -> str:
    keys = action.get("keys", [])
    if not keys:
        return "Touches vides."
    pyautogui.hotkey(*keys)
    return f"Raccourci : {'+'.join(keys)}"

def _kill(action: dict) -> str:
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

def _windows_search(name: str, folder: str | None, find_folder: bool) -> Path | None:
    import pythoncom
    import win32com.client
    from urllib.parse import urlparse, unquote

    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

    conn = win32com.client.Dispatch("ADODB.Connection")
    conn.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")
    rs = win32com.client.Dispatch("ADODB.Recordset")

    kind_filter = "System.Kind = 'folder'" if find_folder else "System.Kind <> 'folder'"

    tokens = re.findall(r"[A-Za-z0-9]+", name)
    if not tokens:
        return None
    contains_expr = " AND ".join(f'"{t}*"' for t in tokens)
    query = (
        f"SELECT TOP 1 System.ItemUrl FROM SystemIndex "
        f"WHERE CONTAINS(System.FileName, '{contains_expr}') AND {kind_filter} "
        f"ORDER BY System.DateModified DESC"
    )

    try:
        rs.Open(query, conn)
        if not rs.EOF:
            url = rs.Fields.Item("System.ItemUrl").Value
            if url:
                parsed = urlparse(url)
                real_path = unquote(parsed.path).lstrip("/")
                real_path = real_path.replace("/", "\\")
                print(f"[Search] Trouvé via index Windows : {real_path}")
                return Path(real_path)
        print(f"[Search] Index Windows : aucun résultat pour '{name}'")
        return None
    finally:
        rs.Close()
        conn.Close()

def _matches_tokens(candidate_name: str, tokens: list[str]) -> bool:
    lname = candidate_name.lower()
    return all(t in lname for t in tokens)

def _find_file(name: str, folder: str, find_folder: bool = False) -> Path | None:
    name = name.lower()
    tokens = re.findall(r"[a-z0-9]+", name)

    try:
        result = _windows_search(name, folder, find_folder)
        if result and result.exists():
            return result
    except Exception as e:
        print(f"[Search] Windows Search indisponible, fallback scan disque : {e}")

    print(f"[Search] Fallback scan disque pour '{name}'")
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
                matches = [p for p in search_path.rglob("*") if p.is_dir() and _matches_tokens(p.name, tokens)]
            else:
                matches = [p for p in search_path.rglob("*") if p.is_file() and p.suffix.lower() != ".lnk" and _matches_tokens(p.name, tokens)]
            if matches:
                return matches[0]
        except PermissionError:
            continue

    home = Path.home()
    try:
        if find_folder:
            matches = [p for p in home.glob("**/*") if p.is_dir() and _matches_tokens(p.name, tokens) and len(p.relative_to(home).parts) <= 3]
        else:
            matches = [p for p in home.glob("**/*") if p.is_file() and p.suffix.lower() != ".lnk" and _matches_tokens(p.name, tokens) and len(p.relative_to(home).parts) <= 3]
        if matches:
            return matches[0]
    except PermissionError:
        pass

    return None

def needs_confirmation(actions: list) -> bool:
    for action in actions:
        if action.get("type", "").lower() in SENSITIVE_ACTIONS:
            return True
    return False

def list_running_apps() -> list[str]:
    apps = set()
    for proc in psutil.process_iter(['name']):
        name = proc.info.get('name', '')
        if name and name.endswith('.exe'):
            apps.add(name)
    return sorted(apps)
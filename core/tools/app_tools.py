import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from core.app_registry import get_registry, find_app
from core.config import WINDOW_WAIT_TIMEOUT, FILE_SEARCH_TIMEOUT, FILE_SEARCH_MAX_RESULTS
from core.tools.registry import Registry, ToolError, READ, LOCAL, CONFIRM
from core.log import get_logger
log = get_logger(__name__)

PROTOCOL_APPS = {
    "ms-windows-store": "ms-windows-store:",
    "microsoft store": "ms-windows-store:",
    "store": "ms-windows-store:",
    "windows store": "ms-windows-store:",
    "settings": "ms-settings:",
    "ms-settings": "ms-settings:",
    "windows settings": "ms-settings:",
    "xbox": "xbox:",
    "calculator": "calculator:",
    "mail": "outlookmail:",
    "calendar": "outlookcal:",
    "maps": "bingmaps:",
    "clock": "ms-clock:",
    "alarms": "ms-clock:",
}

CONSOLE_APPS = {
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "terminal": "cmd.exe",
    "powershell": "powershell.exe",
}

SKIP_DIRS = {"appdata", "node_modules", ".git", "__pycache__", "venv", ".venv", "$recycle.bin", "site-packages"}

_registry_cache: dict | None = None


def _registry() -> dict:
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = get_registry()
    return _registry_cache


def _popen(argv: list[str], **kwargs):
    return subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)


def _startfile(target: str):
    os.startfile(target)


def _expand(path: str) -> Path:
    return Path(os.path.expandvars(path)).expanduser()


def _foreground_window():
    try:
        import win32gui
        return win32gui.GetForegroundWindow()
    except Exception:
        return None


def _wait_for_new_window(prev_hwnd, timeout=WINDOW_WAIT_TIMEOUT):
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


def launch_app(name: str, args: list[str] | None = None, wait: bool = True) -> str:
    name = (name or "").strip()
    if not name:
        raise ToolError("app name is empty")
    args = [str(a) for a in (args or [])]
    key = name.lower()
    prev = _foreground_window() if wait else None

    if key in PROTOCOL_APPS or (key.endswith(":") and "/" not in key and "\\" not in key):
        _startfile(PROTOCOL_APPS.get(key, key))
        launched = PROTOCOL_APPS.get(key, key)
    elif key in CONSOLE_APPS:
        _popen([CONSOLE_APPS[key], *args], creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        launched = CONSOLE_APPS[key]
    else:
        path = find_app(key, _registry())
        if path and Path(path).exists():
            _popen([path, *args])
            launched = Path(path).name
        elif shutil.which(name):
            _popen([shutil.which(name), *args])
            launched = name
        else:
            raise ToolError(f"no installed app found for '{name}'")
    if wait:
        _wait_for_new_window(prev)
    return f"Launched {launched}."


def _windows_search(tokens: list[str], find_folder: bool, limit: int) -> list[Path]:
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
    kind = "System.Kind = 'folder'" if find_folder else "System.Kind <> 'folder'"
    contains = " AND ".join(f'"{t}*"' for t in tokens)
    query = (f"SELECT TOP {int(limit)} System.ItemUrl FROM SystemIndex "
             f"WHERE CONTAINS(System.FileName, '{contains}') AND {kind} ORDER BY System.DateModified DESC")
    found = []
    try:
        rs.Open(query, conn)
        while not rs.EOF:
            url = rs.Fields.Item("System.ItemUrl").Value
            if url:
                found.append(Path(unquote(urlparse(url).path).lstrip("/").replace("/", "\\")))
            rs.MoveNext()
    finally:
        rs.Close()
        conn.Close()
    return found


def _matches(name: str, tokens: list[str]) -> bool:
    lname = name.lower()
    return all(t in lname for t in tokens)


def scan_for(tokens: list[str], roots: list[Path], find_folder: bool, limit: int, deadline: float,
             max_depth: int = 6) -> list[Path]:
    results: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        base_depth = len(root.parts)
        for dirpath, dirnames, filenames in os.walk(root):
            if time.monotonic() > deadline:
                return results
            depth = len(Path(dirpath).parts) - base_depth
            dirnames[:] = [d for d in dirnames if d.lower() not in SKIP_DIRS and not d.startswith(".")]
            if depth >= max_depth:
                dirnames[:] = []
            candidates = dirnames if find_folder else [f for f in filenames if not f.lower().endswith(".lnk")]
            for entry in candidates:
                if _matches(entry, tokens):
                    full = Path(dirpath) / entry
                    if str(full).lower() not in seen:
                        seen.add(str(full).lower())
                        results.append(full)
                        if len(results) >= limit:
                            return results
    return results


def find_paths(name: str, folder: str | None = None, find_folder: bool = False,
               limit: int = FILE_SEARCH_MAX_RESULTS, timeout: float = FILE_SEARCH_TIMEOUT) -> list[Path]:
    tokens = re.findall(r"\w+", (name or "").lower())
    if not tokens:
        raise ToolError("search name is empty")
    deadline = time.monotonic() + timeout
    try:
        hits = [p for p in _windows_search(tokens, find_folder, limit) if p.exists()]
        if hits:
            return hits[:limit]
    except Exception as e:
        log.debug(f"[Search] Windows Search unavailable, scanning disk: {e}")
    home = Path.home()
    roots = []
    if folder:
        roots.append(_expand(folder))
    roots += [home / "Documents", home / "Desktop", home / "Downloads", home]
    unique = []
    for r in roots:
        if r not in unique:
            unique.append(r)
    return scan_for(tokens, unique, find_folder, limit, deadline)


def register(reg: Registry):
    @reg.tool("open_app",
              "Launch an installed application by name (e.g. discord, spotify, code, chrome, settings, calculator). "
              "Waits for its window to take focus, so type_text or press_hotkey can follow directly.",
              {"name": {"type": "string"},
               "args": {"type": "array", "items": {"type": "string"}, "description": "Optional command-line arguments."}},
              ["name"], LOCAL, summarize=lambda a: a.get("name", ""))
    def open_app(ctx, name, args=None):
        return launch_app(name, args)

    @reg.tool("open_path",
              "Open a file, a folder or a URL with its default program. Use %USERPROFILE% for user folders.",
              {"path": {"type": "string"}}, ["path"], LOCAL, summarize=lambda a: a.get("path", ""))
    def open_path(ctx, path):
        path = (path or "").strip()
        if not path:
            raise ToolError("path is empty")
        if re.match(r"^https?://", path, re.I):
            _startfile(path)
            return f"Opened {path}."
        target = _expand(path)
        if not target.exists():
            raise ToolError(f"path not found: {target}. Use find_files to locate it.")
        _startfile(str(target))
        return f"Opened {target}."

    @reg.tool("find_files",
              "Search for files or folders by name (use the exact words the user said). Returns up to a few matching paths.",
              {"name": {"type": "string"},
               "folder": {"type": "string", "description": "Folder to search first, e.g. %USERPROFILE%/Documents"},
               "is_folder": {"type": "boolean"}},
              ["name"], READ, summarize=lambda a: a.get("name", ""))
    def find_files(ctx, name, folder=None, is_folder=False):
        hits = find_paths(name, folder, bool(is_folder))
        if not hits:
            return f"No {'folder' if is_folder else 'file'} matching '{name}' found."
        return "Found:\n" + "\n".join(str(p) for p in hits)

    @reg.tool("open_file",
              "Find a file or folder by name and open it, optionally with a specific app (e.g. app='code').",
              {"name": {"type": "string"}, "folder": {"type": "string"},
               "is_folder": {"type": "boolean"}, "app": {"type": "string"}},
              ["name"], LOCAL, summarize=lambda a: " ".join(filter(None, [a.get("name"), a.get("app") and f"with {a['app']}"])))
    def open_file(ctx, name, folder=None, is_folder=False, app=None):
        hits = find_paths(name, folder, bool(is_folder), limit=1)
        if not hits:
            raise ToolError(f"nothing matching '{name}' found")
        target = hits[0]
        if app:
            app_path = find_app(app.lower(), _registry())
            if app_path and Path(app_path).exists():
                _popen([app_path, str(target)])
            elif shutil.which(app):
                _popen([shutil.which(app), str(target)])
            else:
                raise ToolError(f"app '{app}' not found")
            return f"Opened {target} with {app}."
        _startfile(str(target))
        return f"Opened {target}."

    @reg.tool("type_text", "Type text into the currently focused window (pastes it via the clipboard).",
              {"text": {"type": "string"}}, ["text"], LOCAL)
    def type_text(ctx, text):
        if not text:
            raise ToolError("text is empty")
        import pyautogui
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
        return f"Typed {len(text)} characters."

    @reg.tool("press_hotkey", "Press a keyboard shortcut in the focused window, e.g. ['ctrl', 'c'].",
              {"keys": {"type": "array", "items": {"type": "string"}}}, ["keys"], LOCAL,
              summarize=lambda a: "+".join(a.get("keys") or []))
    def press_hotkey(ctx, keys):
        if not keys:
            raise ToolError("keys are empty")
        import pyautogui
        pyautogui.hotkey(*[str(k).lower() for k in keys])
        return f"Pressed {'+'.join(keys)}."

    @reg.tool("kill_process", "Close an application by process name, e.g. 'spotify.exe'.",
              {"process": {"type": "string"}}, ["process"], CONFIRM,
              confirm_text=lambda a: ("Close application",
                                      f"Force-closes every running {a.get('process', '?')} process. Unsaved work in it will be lost."))
    def kill_process(ctx, process):
        import psutil
        target = (process or "").lower().strip()
        if not target:
            raise ToolError("process name is empty")
        if not target.endswith(".exe"):
            target += ".exe"
        count = 0
        for proc in psutil.process_iter(["name"]):
            if (proc.info.get("name") or "").lower() == target:
                try:
                    proc.terminate()
                    count += 1
                except psutil.Error:
                    pass
        if not count:
            raise ToolError(f"no running process named {target}")
        return f"Closed {count} {target} process(es)."

    @reg.tool("open_workspace",
              "Start a work session: opens VS Code (on a folder if the user named one, ask them which folder first "
              "if unclear), Chrome and Edge.",
              {"folder": {"type": "string", "description": "Folder name the user wants open in VS Code."}},
              [], LOCAL, summarize=lambda a: a.get("folder", ""))
    def open_workspace(ctx, folder=None):
        opened = []
        if folder:
            hits = find_paths(folder, None, True, limit=1)
            if hits:
                launch_app("code", [str(hits[0])], wait=False)
                opened.append(f"VS Code on {hits[0]}")
            else:
                launch_app("code", wait=False)
                opened.append(f"VS Code (folder '{folder}' not found)")
        else:
            launch_app("code", wait=False)
            opened.append("VS Code")
        for app in ("chrome", "msedge"):
            try:
                launch_app(app, wait=False)
                opened.append(app)
            except ToolError as e:
                opened.append(f"{app} failed: {e}")
        return "Workspace: " + ", ".join(opened) + "."

import os
import json
import subprocess
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent.parent / "assets" / "app_registry.json"

# ─── Blacklist — noms d'exe à ne jamais indexer ──────────────────────────────
BLACKLIST_NAMES = {
    "store", "winget", "wt", "cmd", "powershell", "python", "pip", "git",
    "node", "npm", "py", "pyw",
}

# ─── Blacklist — sous-chemins à ignorer entièrement ──────────────────────────
# Tout exe dont le path contient l'un de ces fragments est exclu
BLACKLIST_PATH_FRAGMENTS = [
    # Git internal tools (Unix ports) — on garde git-bash.exe, git-gui.exe etc. à la racine Git\
    "\\Git\\usr\\",
    "\\Git\\mingw64\\",
    "\\Git\\mingw32\\",
    # Android SDK CLI tools
    "\\Android\\Sdk\\",
    # Java JDK binaries
    "\\jdk-",
    "\\jre-",
    # Go build artifacts
    "\\go-build\\",
    # Cached installers
    "\\Package Cache\\",
    # Temp pip artifacts
    "\\Temp\\pip-",
    # LGHUB integrations (applets internes)
    "\\LGHUB\\integrations\\",
    # Office internal rules/markers
    ".exe_Rules",
    # Windows internal AppData markers
    "\\Best_Buy_Canada_Ltd\\",
    "\\iMobie_Inc\\",
]

# ─── Regex filtre — noms d'exe à exclure (appliqué sur le basename) ──────────
BASENAME_FILTER = (
    "uninstall|setup|install|update|crash|helper|register|repair|"
    "installer|updater|patcher|cleanup|touchup|elevat|proxy|hook|"
    "surrogate|injector|broker|launcher_helper|_rules|errorreporter"
)

# ─── Apps connues à lancer via un chemin spécial (versioned folders) ─────────
# Pour ces apps, on fait une recherche ciblée si le scan trouve un mauvais exe
VERSIONED_APPS = {
    "discord": {
        "search_path": Path(os.environ.get("LOCALAPPDATA", "")) / "Discord",
        "pattern": "app-*/Discord.exe",
    },
    "roblox studio": {
        "search_path": Path(os.environ.get("LOCALAPPDATA", "")) / "Roblox" / "Versions",
        "pattern": "*/RobloxStudioBeta.exe",
    },
    "roblox": {
        "search_path": Path(os.environ.get("LOCALAPPDATA", "")) / "Roblox" / "Versions",
        "pattern": "*/RobloxPlayerBeta.exe",
    },
}

# ─── Alias communs ────────────────────────────────────────────────────────────
ALIASES = {
    "discord": ["discord", "discordapp"],
    "spotify": ["spotify"],
    "chrome": ["chrome", "googlechrome", "google chrome"],
    "firefox": ["firefox"],
    "vs code": ["code", "vscode", "visual studio code"],
    "vscode": ["code", "vscode", "visual studio code"],
    "word": ["winword", "microsoft word", "word"],
    "excel": ["excel", "microsoft excel"],
    "powerpoint": ["powerpnt", "microsoft powerpoint", "powerpoint"],
    "outlook": ["outlook", "microsoft outlook"],
    "notepad": ["notepad", "notepad++", "notepadplusplus"],
    "epic games": ["epicgameslauncher", "epic games launcher", "epiclauncher"],
    "steam": ["steam"],
    "nvidia": ["nvidia app", "nvidiaapp", "nvapp"],
    "obs": ["obs", "obs studio", "obs64"],
    "vlc": ["vlc", "vlcportable"],
    "whatsapp": ["whatsapp"],
    "teams": ["teams", "ms-teams", "microsoft teams"],
    "zoom": ["zoom"],
    "brave": ["brave", "brave browser"],
    "edge": ["msedge", "microsoft edge"],
    "msi center": ["msi.centralserver", "msigeneralcontrol"],
}

PS_WIN32 = r"""
$apps = @()


$startMenuPaths = @(
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs",
    "$env:ProgramData\Microsoft\Windows\Start Menu\Programs"
)
foreach ($path in $startMenuPaths) {
    if (Test-Path $path) {
        Get-ChildItem -Path $path -Recurse -Filter "*.lnk" | ForEach-Object {
            $shell = New-Object -ComObject WScript.Shell
            try {
                $shortcut = $shell.CreateShortcut($_.FullName)
                $target = $shortcut.TargetPath
                $targetBase = [System.IO.Path]::GetFileNameWithoutExtension($target).ToLower()
                # Filtre sur le nom du raccourci ET sur le basename de la cible
                if ($target -and $target.EndsWith(".exe") -and (Test-Path $target)) {
                    if ($targetBase -notmatch "uninstall|setup|install|update|crash|helper|register|repair|installer|updater|patcher|cleanup|touchup|elevat|proxy|hook|surrogate|injector|broker|errorreporter") {
                        $apps += [PSCustomObject]@{
                            name = $_.BaseName.ToLower()
                            path = $target
                        }
                    }
                }
            } catch {}
        }
    }
}

# --- Program Files (GUI apps only — depth 3) ---
$programPaths = @(
    "$env:ProgramFiles",
    "${env:ProgramFiles(x86)}",
    "$env:LOCALAPPDATA\Programs"
)
foreach ($base in $programPaths) {
    if (Test-Path $base) {
        Get-ChildItem -Path $base -Recurse -Filter "*.exe" -Depth 3 -ErrorAction SilentlyContinue | ForEach-Object {
            $name = $_.BaseName.ToLower()
            $fullPath = $_.FullName
            # Exclure Git internals, Android SDK, JDK bin, etc.
            if ($fullPath -notmatch "\\Git\\usr\\|\\Git\\mingw|\\Android\\Sdk\\|\\jdk-|\\jre-|\\go-build\\|\\Package Cache\\") {
                if ($name -notmatch "uninstall|setup|install|update|crash|helper|register|repair|installer|updater|patcher|cleanup|touchup|elevat|proxy|hook|surrogate|injector|broker|errorreporter") {
                    $apps += [PSCustomObject]@{
                        name = $name
                        path = $fullPath
                    }
                }
            }
        }
    }
}

# --- AppData Local (Discord, Spotify, etc. — depth 4) ---
$localAppData = "$env:LOCALAPPDATA"
Get-ChildItem -Path $localAppData -Filter "*.exe" -Recurse -Depth 4 -ErrorAction SilentlyContinue | ForEach-Object {
    $name = $_.BaseName.ToLower()
    $fullPath = $_.FullName
    if ($fullPath -notmatch "\\Android\\Sdk\\|\\go-build\\|\\Package Cache\\|\\Temp\\|\\LGHUB\\integrations\\|\\Microsoft\\Office\\16\.0\\") {
        if ($name -notmatch "uninstall|setup|install|update|crash|helper|register|repair|installer|updater|patcher|cleanup|touchup|elevat|proxy|hook|surrogate|injector|broker|errorreporter") {
            $apps += [PSCustomObject]@{
                name = $name
                path = $fullPath
            }
        }
    }
}

# --- AppData Roaming (Zoom, Spotify, etc. — depth 3) ---
$roaming = "$env:APPDATA"
Get-ChildItem -Path $roaming -Filter "*.exe" -Recurse -Depth 3 -ErrorAction SilentlyContinue | ForEach-Object {
    $name = $_.BaseName.ToLower()
    $fullPath = $_.FullName
    if ($name -notmatch "uninstall|setup|install|update|crash|helper|register|repair|installer|updater|patcher|cleanup|touchup|elevat|proxy|hook|surrogate|injector|broker|errorreporter") {
        $apps += [PSCustomObject]@{
            name = $name
            path = $fullPath
        }
    }
}

$apps | Select-Object -Unique name, path | ConvertTo-Json -Compress
"""


# ─── Résolution des apps versionnées (Discord, Roblox, etc.) ─────────────────

def _resolve_versioned(name: str, found_path: str) -> str:
    """
    Si le chemin trouvé est un Update.exe / Installer.exe,
    cherche le vrai exe dans les sous-dossiers connus.
    Retourne le vrai chemin ou le chemin original si rien trouvé.
    """
    basename = Path(found_path).name.lower()
    is_bad = any(x in basename for x in ["update.exe", "installer.exe", "setup.exe"])

    if not is_bad:
        return found_path

    # Cherche dans VERSIONED_APPS
    for key, info in VERSIONED_APPS.items():
        if key in name or name in key:
            search_path = info["search_path"]
            pattern = info["pattern"]
            if search_path.exists():
                matches = sorted(search_path.glob(pattern))
                if matches:
                    # Prend la version la plus récente (tri alphabétique sur app-X.X.XXXX)
                    return str(matches[-1])

    # Fallback générique — cherche un exe du même nom dans le dossier parent
    parent = Path(found_path).parent
    target_name = name.split()[0]  # ex: "discord" depuis "discord"
    candidates = list(parent.glob(f"**/{target_name}.exe"))
    if candidates:
        return str(candidates[0])

    return found_path  # Rien trouvé — on retourne l'original


# ─── Filtre Python (2ème couche après PowerShell) ────────────────────────────

def _is_valid_entry(name: str, path: str) -> bool:
    """Vérifie qu'une entrée nom/path est valide avant indexation."""
    # Nom blacklisté
    if name in BLACKLIST_NAMES:
        return False

    # Fragment de chemin blacklisté
    path_lower = path.lower()
    for fragment in BLACKLIST_PATH_FRAGMENTS:
        if fragment.lower() in path_lower:
            return False

    return True


# ─── Scanner ──────────────────────────────────────────────────────────────────

def build_registry() -> dict:
    """Lance le scan PowerShell et construit le registre propre des apps."""
    print("[Registry] Scan des applications en cours...")

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", PS_WIN32],
            capture_output=True,
            text=True,
            timeout=30
        )
        raw = result.stdout.strip()
        if not raw:
            print("[Registry] Aucun résultat du scan.")
            return {}

        apps_list = json.loads(raw)
        if isinstance(apps_list, dict):
            apps_list = [apps_list]

        # Construire le registre name → path (premier match gagne)
        registry = {}
        skipped = 0
        for app in apps_list:
            name = app.get("name", "").lower().strip()
            path = app.get("path", "")

            if not name or not path:
                continue

            if name in registry:
                continue

            if not _is_valid_entry(name, path):
                skipped += 1
                continue

            # Résolution des apps versionnées (Update.exe → vrai exe)
            path = _resolve_versioned(name, path)

            registry[name] = path

        # Sauvegarder
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)

        print(f"[Registry] {len(registry)} apps indexées ({skipped} exclues) → {REGISTRY_PATH}")
        return registry

    except Exception as e:
        print(f"[Registry] Erreur scan : {e}")
        return {}


def load_registry() -> dict:
    """Charge le registre depuis le cache JSON."""
    if REGISTRY_PATH.exists():
        try:
            with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def get_registry(rebuild: bool = False) -> dict:
    """Retourne le registre — depuis le cache si disponible, sinon rebuild."""
    if rebuild or not REGISTRY_PATH.exists():
        return build_registry()
    return load_registry()


# ─── Lookup ───────────────────────────────────────────────────────────────────

def find_app(name: str, registry: dict) -> str | None:
    """
    Cherche une app dans le registre par nom.
    Stratégie : exact → alias → fuzzy contains → fuzzy exe name.
    Retourne le chemin ou None.
    """
    name = name.lower().strip()

    # 1. Match exact
    if name in registry:
        return registry[name]

    # 2. Alias connus
    for canonical, aliases in ALIASES.items():
        if name in aliases or name == canonical:
            for alias in aliases:
                if alias in registry:
                    return registry[alias]

    # 3. Fuzzy — cherche si le nom est contenu dans une clé du registre
    for key, path in registry.items():
        if name in key or key in name:
            return path

    # 4. Fuzzy inverse — cherche dans le nom du fichier exe
    for key, path in registry.items():
        exe_name = Path(path).stem.lower()
        if name in exe_name or exe_name in name:
            return path

    return None
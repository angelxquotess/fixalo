#desktop.py
from __future__ import annotations
import os
import sys
import json
import shutil
import subprocess
import tempfile
import platform
from pathlib import Path
from datetime import datetime

try:
    import pyautogui
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


# ---------------------------------------------------------------------
# Shortcut fast-path
# ---------------------------------------------------------------------
_SHORTCUT_KEYWORDS = (
    "shortcut", "shortcuts",
    "scorciatoia", "scorciatoie",
    "collegamento",
)

# Map of folder aliases (both English and Italian) -> resolver
def _known_folders() -> dict:
    home = Path.home()
    def _first_existing(*names):
        for n in names:
            p = home / n
            if p.exists():
                return p
        return home / names[0]

    return {
        # desktop
        "desktop":     _first_existing("Desktop", "Scrivania"),
        "scrivania":   _first_existing("Desktop", "Scrivania"),
        # downloads
        "downloads":   _first_existing("Downloads", "Download", "Scaricati"),
        "download":    _first_existing("Downloads", "Download", "Scaricati"),
        "scaricati":   _first_existing("Downloads", "Download", "Scaricati"),
        # documents
        "documents":   _first_existing("Documents", "Documenti"),
        "documenti":   _first_existing("Documents", "Documenti"),
        # pictures / images
        "pictures":    _first_existing("Pictures", "Immagini"),
        "immagini":    _first_existing("Pictures", "Immagini"),
        # videos
        "videos":      _first_existing("Videos", "Video"),
        "video":       _first_existing("Videos", "Video"),
        # music
        "music":       _first_existing("Music", "Musica"),
        "musica":      _first_existing("Music", "Musica"),
        # home
        "home":        home,
    }


def _active_explorer_folder() -> Path | None:
    """Return the folder currently open in the foreground Windows
    Explorer window, or None if not on Windows / no Explorer window."""
    if _OS != "Windows":
        return None
    try:
        import ctypes
        from win32com.client import Dispatch  # type: ignore

        fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
        shell = Dispatch("Shell.Application")
        for w in shell.Windows():
            try:
                if int(w.HWND) == int(fg_hwnd):
                    p = w.Document.Folder.Self.Path
                    if p:
                        return Path(p)
            except Exception:
                continue
        # Fallback: first open Explorer window
        for w in shell.Windows():
            try:
                p = w.Document.Folder.Self.Path
                if p:
                    return Path(p)
            except Exception:
                continue
    except Exception:
        pass
    return None


def _detect_shortcut_intent(task: str) -> Path | None:
    """If `task` describes creating a desktop shortcut for a folder,
    return the resolved folder Path. Otherwise return None.
    """
    if not task:
        return None
    t = task.lower()
    if not any(kw in t for kw in _SHORTCUT_KEYWORDS):
        return None

    # Strip the "on the desktop" location hint before resolving the
    # target folder — the desktop is always the *destination* of the
    # shortcut, never the source (unless the user is explicit about it).
    for phrase in (
        "on the desktop", "onto the desktop", "to the desktop",
        "sul desktop", "sulla scrivania", "sul mio desktop",
        "sulla mia scrivania",
    ):
        t = t.replace(phrase, " ")

    # Try to resolve target folder from keywords first
    known = _known_folders()
    for alias, path in known.items():
        # match whole word (very forgiving)
        if f" {alias}" in f" {t} " or t.startswith(alias):
            return path

    # References to "this folder / current folder / selected folder"
    context_kws = (
        "this folder", "current folder", "selected folder", "open folder",
        "questa cartella", "cartella corrente", "cartella selezionata",
        "cartella aperta", "cartella attuale",
    )
    if any(kw in t for kw in context_kws):
        p = _active_explorer_folder()
        if p is not None:
            return p
        # graceful fallback: user's Desktop itself makes little sense; use
        # the current working directory of the Jarvis process instead
        try:
            return Path.cwd()
        except Exception:
            return Path.home()

    # If the task mentions "folder" or "cartella" without a specific
    # name but we have an active Explorer window, use that.
    if "folder" in t or "cartella" in t or "directory" in t:
        p = _active_explorer_folder()
        if p is not None:
            return p

    return None


def _create_folder_shortcut_on_desktop(target: Path) -> str:
    """Create a *plain* folder shortcut on the user's Desktop pointing
    to `target`. Uses pywin32 (WScript.Shell) → PowerShell → .desktop
    file, depending on the OS.
    """
    try:
        target = Path(target).expanduser().resolve()
    except Exception:
        return f"Sir, il percorso '{target}' non è valido."

    if not target.exists():
        return f"Sir, la cartella '{target}' non esiste."
    if not target.is_dir():
        return f"Sir, '{target}' non è una cartella."

    desk = _get_desktop()
    try:
        desk.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    label = target.name or str(target).strip("/\\") or "Shortcut"

    if _OS == "Windows":
        lnk_path = desk / f"{label}.lnk"
        # Guarantee uniqueness
        idx = 2
        while lnk_path.exists():
            lnk_path = desk / f"{label} ({idx}).lnk"
            idx += 1

        # 1) Try pywin32 (silent, no console window)
        try:
            import pythoncom  # noqa: F401  # type: ignore
            from win32com.client import Dispatch  # type: ignore
            shell = Dispatch("WScript.Shell")
            sc = shell.CreateShortCut(str(lnk_path))
            sc.Targetpath = str(target)
            sc.WorkingDirectory = str(target)
            sc.Description = f"Shortcut to {target} (JARVIS)"
            sc.save()
            if lnk_path.exists():
                return f"Ho messo la scorciatoia '{label}' sul tuo desktop, capo."
        except Exception as exc:
            print(f"[Desktop] pywin32 shortcut failed: {exc}")

        # 2) PowerShell fallback
        try:
            ps_lnk = str(lnk_path).replace("'", "''")
            ps_tgt = str(target).replace("'", "''")
            script = (
                f"$ws = New-Object -ComObject WScript.Shell; "
                f"$s = $ws.CreateShortcut('{ps_lnk}'); "
                f"$s.TargetPath = '{ps_tgt}'; "
                f"$s.WorkingDirectory = '{ps_tgt}'; "
                f"$s.Save()"
            )
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, timeout=10, creationflags=creationflags,
            )
            if lnk_path.exists():
                return f"Ho messo la scorciatoia '{label}' sul tuo desktop, capo."
        except Exception as exc:
            print(f"[Desktop] PowerShell shortcut failed: {exc}")

        return f"Non sono riuscito a creare la scorciatoia sul desktop ({lnk_path})."

    if _OS == "Darwin":
        # Use a symbolic link — macOS treats .command files as scripts,
        # a symlink is the closest analogue to a folder shortcut.
        link_path = desk / label
        idx = 2
        while link_path.exists():
            link_path = desk / f"{label} ({idx})"
            idx += 1
        try:
            os.symlink(str(target), str(link_path))
            return f"Ho creato un collegamento a '{label}' sul desktop, capo."
        except Exception as exc:
            return f"Non sono riuscito a creare il collegamento: {exc}"

    # Linux → .desktop file (Directory type)
    desktop_file = desk / f"{label}.desktop"
    idx = 2
    while desktop_file.exists():
        desktop_file = desk / f"{label} ({idx}).desktop"
        idx += 1
    try:
        content = (
            "[Desktop Entry]\n"
            "Type=Link\n"
            "Version=1.0\n"
            f"Name={label}\n"
            f"URL=file://{target}\n"
            "Icon=folder\n"
        )
        desktop_file.write_text(content, encoding="utf-8")
        try:
            desktop_file.chmod(0o755)
        except Exception:
            pass
        return f"Ho creato '{label}.desktop' sul desktop, capo."
    except Exception as exc:
        return f"Non sono riuscito a creare il collegamento: {exc}"


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def _get_api_key() -> str:
    path = _get_base_dir() / "config" / "api_keys.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]
    
def _get_desktop() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DESKTOP_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Desktop"

def _build_sandbox() -> dict:
    import time

    safe_builtins = {
        "print": print,
        "len": len, "str": str, "int": int, "float": float,
        "bool": bool, "list": list, "dict": dict, "tuple": tuple,
        "range": range, "enumerate": enumerate, "sorted": sorted,
        "isinstance": isinstance, "hasattr": hasattr, "getattr": getattr,
        "max": max, "min": min, "sum": sum, "abs": abs,
        "zip": zip, "map": map, "filter": filter,
    }

    sandbox = {
        "__builtins__": safe_builtins,
        "Path": Path,
        "time": time,
        "shutil": type("shutil", (), {
            "copy2":      shutil.copy2,
            "copytree":   shutil.copytree,
            "disk_usage": shutil.disk_usage,
        })(),
        "os_path": os.path,  
    }

    if _PYAUTOGUI:
        sandbox["pyautogui"] = pyautogui

    if _OS == "Windows":
        try:
            import ctypes
            import winreg
            sandbox["ctypes"] = ctypes
            sandbox["winreg"] = type("winreg", (), {
                # Sadece okuma
                "OpenKey":      winreg.OpenKey,
                "QueryValueEx": winreg.QueryValueEx,
                "HKEY_CURRENT_USER": winreg.HKEY_CURRENT_USER,
            })()
        except ImportError:
            pass

    return sandbox


def _execute_generated_code(code: str, player=None) -> str:
    if not code or code.strip() == "UNSAFE":
        return "This action cannot be performed safely."

    # Kod temizleme
    if code.startswith("```"):
        lines = code.split("\n")
        code  = "\n".join(lines[1:-1]).strip()

    sandbox      = _build_sandbox()
    output_lines = []
    sandbox["__builtins__"]["print"] = lambda *a: output_lines.append(" ".join(str(x) for x in a))

    try:
        exec(compile(code, "<jarvis_desktop>", "exec"), sandbox)
        return "\n".join(output_lines) if output_lines else "Done."
    except Exception as e:
        print(f"[Desktop] Exec error: {e}\nCode:\n{code[:300]}")
        return f"Execution error: {e}"


def _ask_gemini_for_desktop_action(task: str) -> str:

    from google import genai as _genai
    _client = _genai.Client(api_key=_get_api_key())

    desktop = str(_get_desktop())

    os_specific = ""
    if _OS == "Windows":
        os_specific = "- ctypes (Windows API calls, read-only)\n- winreg (registry READ only)"
    elif _OS == "Darwin":
        os_specific = "- subprocess is NOT available; use pyautogui or Path only"
    else:
        os_specific = "- subprocess is NOT available; use pyautogui or Path only"

    prompt = f"""You are a desktop automation assistant.
Current OS: {_OS}
Desktop path: {desktop}

Generate safe Python code to accomplish the task below.
Allowed modules ONLY:
- pyautogui (mouse, keyboard — if needed)
- pathlib.Path (file/folder inspection only, no deletion)
- shutil.copy2, shutil.copytree, shutil.disk_usage (NO move, NO rmtree)
- os_path (os.path equivalent, read-only)
- time.sleep
{os_specific}

Hard rules:
- NO file deletion (no unlink, no rmtree, no remove)
- NO subprocess calls
- NO exec() or eval() inside the code
- NO import statements (modules are pre-injected)
- NO file write operations except explicitly requested
- If task cannot be done safely with these tools, output exactly: UNSAFE

Output ONLY the Python code. No explanation, no markdown, no backticks.

Task: {task}"""

    try:
        response = _client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        code = response.text.strip()
        if code.startswith("```"):
            lines = code.split("\n")
            code  = "\n".join(lines[1:-1]).strip()
        return code
    except Exception as e:
        return f"ERROR: {e}"

def set_wallpaper(image_path: str) -> str:
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        return f"Image not found: {image_path}"
    if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        return f"Unsupported format: {path.suffix}. Use jpg, png, bmp or webp."

    try:
        if _OS == "Windows":
            import ctypes
            if path.suffix.lower() in {".webp", ".png"}:
                try:
                    from PIL import Image
                    bmp_path = Path(tempfile.mktemp(suffix=".bmp"))
                    Image.open(path).convert("RGB").save(bmp_path, "BMP")
                    path = bmp_path
                except ImportError:
                    pass 
            ctypes.windll.user32.SystemParametersInfoW(20, 0, str(path), 3)
            return f"Wallpaper set: {path.name}"

        elif _OS == "Darwin":
            script = (
                f'tell application "System Events" to tell every desktop to '
                f'set picture to POSIX file "{path}"'
            )
            subprocess.run(["osascript", "-e", script], capture_output=True)
            return f"Wallpaper set: {path.name}"

        else:
            desktop_env = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
            uri = f"file://{path}"

            if "gnome" in desktop_env or "unity" in desktop_env:
                subprocess.run([
                    "gsettings", "set", "org.gnome.desktop.background",
                    "picture-uri", uri
                ], capture_output=True)
                subprocess.run([
                    "gsettings", "set", "org.gnome.desktop.background",
                    "picture-uri-dark", uri
                ], capture_output=True)

            elif "kde" in desktop_env:
                # KDE Plasma
                script = f"""
var allDesktops = desktops();
for (var i = 0; i < allDesktops.length; i++) {{
    d = allDesktops[i];
    d.wallpaperPlugin = "org.kde.image";
    d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    d.writeConfig("Image", "file://{path}");
}}
"""
                subprocess.run(
                    ["qdbus", "org.kde.plasmashell", "/PlasmaShell",
                     "org.kde.PlasmaShell.evaluateScript", script],
                    capture_output=True
                )

            elif "xfce" in desktop_env:
                subprocess.run([
                    "xfconf-query", "-c", "xfce4-desktop",
                    "-p", "/backdrop/screen0/monitor0/workspace0/last-image",
                    "-s", str(path)
                ], capture_output=True)

            else:
                result = subprocess.run(
                    ["feh", "--bg-scale", str(path)],
                    capture_output=True
                )
                if result.returncode != 0:
                    return (
                        f"Could not set wallpaper automatically on {desktop_env}. "
                        f"Try manually or install 'feh'."
                    )

            return f"Wallpaper set: {path.name}"

    except Exception as e:
        return f"Could not set wallpaper: {e}"


def set_wallpaper_from_url(url: str) -> str:
    try:
        import urllib.request
        suffix = Path(url.split("?")[0]).suffix or ".jpg"
        tmp    = Path(tempfile.mktemp(suffix=suffix))
        urllib.request.urlretrieve(url, str(tmp))
        result = set_wallpaper(str(tmp))
        try:
            tmp.unlink()
        except Exception:
            pass
        return result
    except Exception as e:
        return f"Could not download wallpaper: {e}"


def get_current_wallpaper() -> str:
    try:
        if _OS == "Windows":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop"
            )
            val, _ = winreg.QueryValueEx(key, "Wallpaper")
            winreg.CloseKey(key)
            return f"Current wallpaper: {val}"

        elif _OS == "Darwin":
            script = (
                'tell application "System Events" to get picture of desktop 1'
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True
            )
            return f"Current wallpaper: {result.stdout.strip()}"

        else:
            desktop_env = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
            if "gnome" in desktop_env or "unity" in desktop_env:
                result = subprocess.run(
                    ["gsettings", "get", "org.gnome.desktop.background", "picture-uri"],
                    capture_output=True, text=True
                )
                return f"Current wallpaper: {result.stdout.strip()}"
            return "Wallpaper path retrieval not supported for this desktop environment."

    except Exception as e:
        return f"Could not get wallpaper: {e}"

FILE_TYPE_MAP = {
    "Images":      {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".heic"},
    "Documents":   {".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx",
                    ".ppt", ".pptx", ".csv", ".odt", ".ods", ".odp"},
    "Videos":      {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
    "Music":       {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
    "Archives":    {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
    "Code":        {".py", ".js", ".ts", ".html", ".css", ".json", ".xml",
                    ".cpp", ".java", ".cs", ".go", ".rs", ".sh", ".php"},
    "Executables": {".exe", ".msi", ".bat", ".cmd", ".sh", ".appimage", ".deb", ".rpm"},
}

_SKIP_EXTENSIONS = {
    "Windows": {".lnk", ".url"},
    "Darwin":  {".webloc"},
    "Linux":   {".desktop"},
}


def organize_desktop(mode: str = "by_type") -> str:
    desktop       = _get_desktop()
    skip_exts     = _SKIP_EXTENSIONS.get(_OS, set())
    moved, skipped = [], []

    for item in desktop.iterdir():
        if item.is_dir() or item.name.startswith("."):
            continue
        if item.suffix.lower() in skip_exts:
            continue

        if mode == "by_date":
            mtime       = datetime.fromtimestamp(item.stat().st_mtime)
            folder_name = mtime.strftime("%Y-%m")
        else:
            ext         = item.suffix.lower()
            folder_name = "Others"
            for folder, exts in FILE_TYPE_MAP.items():
                if ext in exts:
                    folder_name = folder
                    break

        target_dir = desktop / folder_name
        target_dir.mkdir(exist_ok=True)
        new_path = target_dir / item.name

        if new_path.exists():
            skipped.append(item.name)
            continue

        shutil.move(str(item), str(new_path))
        moved.append(f"{item.name} → {folder_name}/")

    result = f"Desktop organized ({mode}): {len(moved)} files moved."
    if moved:
        result += "\n" + "\n".join(moved[:8])
        if len(moved) > 8:
            result += f"\n... and {len(moved) - 8} more."
    if skipped:
        result += f"\n{len(skipped)} file(s) skipped (name conflict)."
    return result


def list_desktop() -> str:
    desktop = _get_desktop()
    items   = []
    for item in sorted(desktop.iterdir()):
        if item.name.startswith("."):
            continue
        if item.is_dir():
            try:
                count = len(list(item.iterdir()))
            except PermissionError:
                count = "?"
            items.append(f"📁 {item.name}/ ({count} items)")
        else:
            size     = item.stat().st_size
            size_str = (
                f"{size / 1024:.1f} KB" if size < 1024 * 1024
                else f"{size / 1024 / 1024:.1f} MB"
            )
            items.append(f"📄 {item.name} ({size_str})")

    if not items:
        return "Desktop is empty."
    return f"Desktop ({len(items)} items):\n" + "\n".join(items)


def clean_desktop() -> str:
    desktop     = _get_desktop()
    skip_exts   = _SKIP_EXTENSIONS.get(_OS, set())
    today       = datetime.now().strftime("%Y-%m-%d")
    archive_dir = desktop / f"Desktop Archive {today}"
    archive_dir.mkdir(exist_ok=True)

    moved = 0
    for item in desktop.iterdir():
        if item.is_dir() or item.name.startswith("."):
            continue
        if item.suffix.lower() in skip_exts:
            continue
        new_path = archive_dir / item.name
        if not new_path.exists():
            shutil.move(str(item), str(new_path))
            moved += 1

    return f"Desktop cleaned: {moved} files archived to '{archive_dir.name}'."


def get_desktop_stats() -> str:
    desktop    = _get_desktop()
    files      = [i for i in desktop.iterdir() if i.is_file()]
    folders    = [i for i in desktop.iterdir() if i.is_dir()]
    total_size = sum(f.stat().st_size for f in files if f.exists())
    size_str   = (
        f"{total_size / 1024:.1f} KB" if total_size < 1024 * 1024
        else f"{total_size / 1024 / 1024:.1f} MB"
    )
    return (
        f"Desktop stats ({_OS}):\n"
        f"  Files   : {len(files)}\n"
        f"  Folders : {len(folders)}\n"
        f"  Size    : {size_str}\n"
        f"  Path    : {desktop}"
    )

def desktop_control(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    parameters:
        action : wallpaper | wallpaper_url | current_wallpaper |
                 organize  | clean | list | stats |
                 task (AI-powered)
        path   : image path for 'wallpaper'
        url    : image URL for 'wallpaper_url'
        mode   : 'by_type' or 'by_date' for 'organize'
        task   : natural language description for AI-powered actions
    """
    params = parameters or {}
    action = params.get("action", "").lower().strip()
    task   = params.get("task", "").strip()

    if player:
        player.write_log(f"[desktop] {action or task[:40]}")

    try:
        if action == "wallpaper":
            path = params.get("path", "")
            return set_wallpaper(path) if path else "No image path provided."

        elif action == "wallpaper_url":
            url = params.get("url", "")
            return set_wallpaper_from_url(url) if url else "No URL provided."

        elif action == "current_wallpaper":
            return get_current_wallpaper()

        elif action == "organize":
            return organize_desktop(params.get("mode", "by_type"))

        elif action == "clean":
            return clean_desktop()

        elif action == "list":
            return list_desktop()

        elif action == "stats":
            return get_desktop_stats()

        elif action == "task" or task:
            actual_task = task or params.get("description", "")
            if not actual_task:
                return "Please describe what you want to do on the desktop."

            # ---- FAST PATH: shortcut creation ----------------------------
            # Gemini refuses to write COM / subprocess code (creating a
            # .lnk requires WScript.Shell or PowerShell), so any request
            # like "create a shortcut for X on the desktop" ends up
            # returning UNSAFE. We intercept the intent here and hand it
            # over to a native helper that speaks pywin32 / PowerShell /
            # .desktop directly.
            shortcut_hit = _detect_shortcut_intent(actual_task)
            if shortcut_hit is not None:
                print(f"[Desktop] shortcut fast-path: {shortcut_hit!r}")
                if player:
                    player.write_log("[Desktop] Creating desktop shortcut...")
                return _create_folder_shortcut_on_desktop(shortcut_hit)

            print(f"[Desktop] Asking Gemini: {actual_task}")
            if player:
                player.write_log("[Desktop] Generating action...")

            code = _ask_gemini_for_desktop_action(actual_task)
            return _execute_generated_code(code, player=player)

        else:
            if action:
                code = _ask_gemini_for_desktop_action(action)
                return _execute_generated_code(code, player=player)
            return "No action or task specified."

    except Exception as e:
        print(f"[Desktop] Error: {e}")
        return f"Desktop control error: {e}"
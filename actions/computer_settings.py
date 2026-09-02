#computer_settings.py
import json
import re
import sys
import time
import subprocess
import platform
from datetime import datetime
from pathlib import Path

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.05
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

try:
    import pygetwindow as gw
    _PYGETWINDOW = True
except ImportError:
    _PYGETWINDOW = False

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

if _OS == "Windows":
    _WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW}
else:
    _WIN_HIDE: dict = {}


# Titles for the "Save As" dialog across languages / OSes we care about.
_SAVE_AS_TITLES = (
    "save as",
    "salva con nome",
    "save",
    "salva",
    "enregistrer sous",
    "guardar como",
    "speichern unter",
)


# Keywords used to recognise the currently-focused window as an editor that
# actually has a "save before close" concept (Notepad, VSCode, Word, ecc.).
# Case-insensitive substring match against the active window title.
_EDITOR_WINDOW_KEYWORDS = (
    "notepad",             # Windows Notepad + Notepad++
    "blocco note",         # Italian Notepad
    "wordpad",
    "visual studio code",  # VSCode window title suffix
    "vscode",
    "- code",              # VSCode fallback ("filename - Visual Studio Code")
    "sublime text",
    "atom",
    "brackets",
    "textedit",            # macOS
    "textmate",
    "gedit",
    "kate",
    "kwrite",
    "nano",
    "vim",
    "gvim",
    "emacs",
    "microsoft word",
    "libreoffice writer",
    "libreoffice calc",
    "libreoffice impress",
    "openoffice",
    "excel",
    "powerpoint",
    "onenote",
    "pycharm",
    "intellij",
    "webstorm",
    "phpstorm",
    "clion",
    "goland",
    "rider",
    "android studio",
    "eclipse",
    "netbeans",
    "xcode",
    "notepad++",
    "obsidian",
    "typora",
    "bbedit",
    "geany",
    "scite",
    "editplus",
    "ultraedit",
    "cursor",              # Cursor editor
    "zed",
)

# Titles / substrings identifying the assistant's own UI windows so that
# "close" commands issued while our UI is focused close *that* window
# (i.e. the assistant itself) without prompting for save.
_OWN_UI_WINDOW_KEYWORDS = (
    "jarvis",
    "daidai",
)


def _get_active_window_title() -> str:
    """Return the title of the currently-focused window (lower-cased)."""
    if not _PYGETWINDOW:
        return ""
    try:
        win = gw.getActiveWindow()
        if win and getattr(win, "title", None):
            return str(win.title).strip().lower()
    except Exception as e:
        print(f"[Settings] _get_active_window_title failed: {e}")
    return ""


# Common aliases (english + italian) for app names → substrings to match
# in window titles / process names. Keep lowercase.
_APP_ALIASES = {
    "chrome":       ("google chrome", "chrome"),
    "firefox":      ("mozilla firefox", "firefox"),
    "edge":         ("microsoft edge", "edge"),
    "opera":        ("opera",),
    "brave":        ("brave",),
    "safari":       ("safari",),
    "notepad":      ("notepad", "blocco note"),
    "blocco_note":  ("notepad", "blocco note"),
    "wordpad":      ("wordpad",),
    "vscode":       ("visual studio code", "- code", "vscode"),
    "visual_studio_code": ("visual studio code", "- code", "vscode"),
    "code":         ("visual studio code", "- code", "vscode"),
    "cursor":       ("cursor",),
    "sublime":      ("sublime text",),
    "sublime_text": ("sublime text",),
    "atom":         ("atom",),
    "notepad++":    ("notepad++",),
    "notepadpp":    ("notepad++",),
    "word":         ("microsoft word", "- word"),
    "microsoft_word": ("microsoft word", "- word"),
    "excel":        ("excel",),
    "powerpoint":   ("powerpoint",),
    "onenote":      ("onenote",),
    "libreoffice":  ("libreoffice",),
    "pycharm":      ("pycharm",),
    "intellij":     ("intellij",),
    "webstorm":     ("webstorm",),
    "phpstorm":     ("phpstorm",),
    "clion":        ("clion",),
    "goland":       ("goland",),
    "android_studio": ("android studio",),
    "xcode":        ("xcode",),
    "obsidian":     ("obsidian",),
    "typora":       ("typora",),
    "textedit":     ("textedit",),
    "spotify":      ("spotify",),
    "discord":      ("discord",),
    "telegram":     ("telegram",),
    "whatsapp":     ("whatsapp",),
    "slack":        ("slack",),
    "teams":        ("microsoft teams", "teams"),
    "zoom":         ("zoom"),
    "vlc":          ("vlc",),
    "youtube":      ("youtube",),
    "explorer":     ("file explorer", "esplora file"),
    "file_explorer": ("file explorer", "esplora file"),
    "esplora_file": ("file explorer", "esplora file"),
    "cmd":          ("command prompt", "prompt dei comandi", "cmd.exe"),
    "powershell":   ("powershell",),
    "terminal":     ("terminal",),
}


def _normalise_target(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def _target_search_terms(target_app: str) -> tuple[str, ...]:
    """Return lowercase substrings to look for in window titles."""
    key = _normalise_target(target_app)
    if key in _APP_ALIASES:
        return _APP_ALIASES[key]
    # Fallback: use the raw name as-is, plus its space-form.
    return (key.replace("_", " "), key)


def _find_window_for_app(target_app: str):
    """Return the first window matching target_app, or None."""
    if not _PYGETWINDOW or not target_app:
        return None
    terms = _target_search_terms(target_app)
    try:
        wins = [w for w in gw.getAllWindows()
                if getattr(w, "title", None) and w.title.strip()]
    except Exception as e:
        print(f"[Settings] _find_window_for_app enumeration failed: {e}")
        return None
    # Prefer visible (non-minimised) windows first.
    for w in wins:
        title = w.title.lower()
        if any(t in title for t in terms):
            return w
    return None


def _focus_window(win) -> bool:
    """Bring ``win`` to the foreground. Returns True on success."""
    if win is None:
        return False
    try:
        try:
            if getattr(win, "isMinimized", False):
                win.restore()
        except Exception:
            pass
        try:
            win.activate()
        except Exception:
            # On Windows activate() sometimes throws even when it works.
            pass
        time.sleep(0.25)
        return True
    except Exception as e:
        print(f"[Settings] _focus_window failed: {e}")
        return False


def _active_window_matches(target_app: str) -> bool:
    if not target_app:
        return True
    terms = _target_search_terms(target_app)
    title = _get_active_window_title()
    return bool(title) and any(t in title for t in terms)


def _active_window_is_editor(title_override: str | None = None) -> bool:
    """
    True if the window looks like a document editor (Notepad, VSCode, Word, …).
    Only these apps should trigger the "save before closing?" prompt.

    If ``title_override`` is provided it is checked against the editor keyword
    list instead of the currently-focused window. This lets close-app handle
    the case "chiudi Notepad" while the user is still on Jarvis's own UI.

    If we cannot inspect windows (pygetwindow missing or the call fails) and
    no override is provided, return False so we DON'T ask spuriously.
    """
    title = (title_override or _get_active_window_title() or "").lower()
    if not title:
        return False
    if any(k in title for k in _OWN_UI_WINDOW_KEYWORDS):
        # Jarvis's own UI is never an editor.
        return False
    return any(k in title for k in _EDITOR_WINDOW_KEYWORDS)


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def _get_api_key() -> str:
    path = _get_base_dir() / "config" / "api_keys.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]

def _get_macos_wifi_interface() -> str:
    try:
        result = subprocess.run(
            ["networksetup", "-listallhardwareports"],
            capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.splitlines()
        for i, line in enumerate(lines):
            if "Wi-Fi" in line or "AirPort" in line:
                for j in range(i, min(i + 4, len(lines))):
                    if lines[j].startswith("Device:"):
                        return lines[j].split(":", 1)[1].strip()
    except Exception:
        pass
    return "en0"


# --------------------------------------------------------------------------- #
#  Save-As dialog helpers                                                     #
# --------------------------------------------------------------------------- #
def _is_save_as_dialog_open() -> bool:
    """
    Return True if a Save/Save-As dialog is currently open on the desktop.

    Uses pygetwindow when available (Windows). If pygetwindow is not
    installed we cannot inspect window titles reliably, so we conservatively
    return True: the caller will then type a filename + Enter, which is
    harmless when the dialog is actually open and a no-op otherwise
    (Alt+F4 will still close the app in the following step).
    """
    if not _PYGETWINDOW:
        return True
    try:
        for title in gw.getAllTitles():
            if not title:
                continue
            low = title.strip().lower()
            if any(low == t or low.startswith(t) for t in _SAVE_AS_TITLES):
                return True
    except Exception as e:
        print(f"[Settings] _is_save_as_dialog_open failed: {e}")
        return True
    return False


def _sanitize_filename(name: str) -> str:
    """Strip characters that are illegal in file names on Windows/macOS."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip()
    name = re.sub(r"\s+", "_", name)
    return name or "untitled"


def _smart_type(text: str) -> None:
    """Type ``text`` using clipboard-paste when possible, else keystrokes."""
    if not text:
        return
    if _PYPERCLIP:
        try:
            pyperclip.copy(str(text))
            time.sleep(0.15)
            if _OS == "Darwin":
                pyautogui.hotkey("command", "v")
            else:
                pyautogui.hotkey("ctrl", "v")
            return
        except Exception as e:
            print(f"[Settings] _smart_type clipboard failed: {e}")
    pyautogui.write(str(text), interval=0.02)


def _handle_save_as_dialog(filename: str | None) -> str:
    """
    Assuming a Save-As dialog is open and its filename field is already
    focused (default on Windows/macOS): just type the filename and press
    Enter — the OS saves it to whatever directory the dialog currently
    points at.

      - use ``filename`` if provided (the LLM should choose a concept-based
        name from the document content, e.g. "lettera.txt" or
        "poesia_amore.txt");
      - otherwise fallback to ``untitled_<ts>.txt``.

    Returns the filename that was typed.
    """
    if filename:
        name = _sanitize_filename(Path(filename).name)
    else:
        name = f"untitled_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    _smart_type(name)
    time.sleep(0.2)
    pyautogui.press("enter")
    return name


def volume_up():
    if _OS == "Windows":
        for _ in range(5): pyautogui.press("volumeup")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            "set volume output volume (output volume of (get volume settings) + 10)"],
            capture_output=True)
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"],
            capture_output=True)

def volume_down():
    if _OS == "Windows":
        for _ in range(5): pyautogui.press("volumedown")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            "set volume output volume (output volume of (get volume settings) - 10)"],
            capture_output=True)
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"],
            capture_output=True)

def volume_mute():
    if _OS == "Windows":
        pyautogui.press("volumemute")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", "set volume with output muted"],
            capture_output=True)
    else:
        subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
            capture_output=True)

def volume_set(value: int):
    value = max(0, min(100, int(value)))
    if _OS == "Windows":
        try:
            import math
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices   = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol       = cast(interface, POINTER(IAudioEndpointVolume))
            vol_db    = -65.25 if value == 0 else max(-65.25, 20 * math.log10(value / 100))
            vol.SetMasterVolumeLevel(vol_db, None)
            return
        except Exception as e:
            print(f"[Settings] pycaw failed, using keypress fallback: {e}")
            pyautogui.press("volumemute")
            pyautogui.press("volumemute")
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e", f"set volume output volume {value}"],
            capture_output=True)
        return
    else:
        subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{value}%"],
            capture_output=True)
        return

def brightness_up():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to key code 144'],
            capture_output=True)
    elif _OS == "Linux":
        if subprocess.run(["which", "brightnessctl"],
                capture_output=True).returncode == 0:
            subprocess.run(["brightnessctl", "set", "+10%"], capture_output=True)
        else:
            subprocess.run(
                'xrandr --output $(xrandr | grep " connected" | head -1 | cut -d " " -f1)'
                ' --brightness $(python3 -c "import subprocess; '
                'b=float(subprocess.check_output([\"xrandr\",\"--verbose\"]).decode()'
                '.split(\"Brightness:\")[1].split()[0]); print(min(1.0,b+0.1))")',
                shell=True, capture_output=True
            )
    else:
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods)"
                 ".WmiSetBrightness(1, [math]::Min(100, "
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness).CurrentBrightness + 10))"],
                capture_output=True, timeout=5, **_WIN_HIDE
            )
        except Exception as e:
            print(f"[Settings] Brightness up failed on Windows: {e}")

def brightness_down():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to key code 145'],
            capture_output=True)
    elif _OS == "Linux":
        if subprocess.run(["which", "brightnessctl"],
                capture_output=True).returncode == 0:
            subprocess.run(["brightnessctl", "set", "10%-"], capture_output=True)
        else:
            subprocess.run(
                'xrandr --output $(xrandr | grep " connected" | head -1 | cut -d " " -f1)'
                ' --brightness $(python3 -c "import subprocess; '
                'b=float(subprocess.check_output([\"xrandr\",\"--verbose\"]).decode()'
                '.split(\"Brightness:\")[1].split()[0]); print(max(0.1,b-0.1))")',
                shell=True, capture_output=True
            )
    else:
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods)"
                 ".WmiSetBrightness(1, [math]::Max(0, "
                 "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness).CurrentBrightness - 10))"],
                capture_output=True, timeout=5, **_WIN_HIDE
            )
        except Exception as e:
            print(f"[Settings] Brightness down failed on Windows: {e}")

def close_app():
    if _OS == "Darwin": pyautogui.hotkey("command", "q")
    else:               pyautogui.hotkey("alt", "f4")


def _dismiss_save_dialog_dont_save():
    """
    Dopo Alt+F4 / Cmd+Q, se compare il dialog "Vuoi salvare?" (Notepad, editor, ecc.)
    l'accelleratore 'N' scegli "Non salvare" / "Don't save" (universale su Windows).
    Su macOS l'accelleratore è ⌘+D.
    """
    time.sleep(0.5)
    if _OS == "Darwin":
        pyautogui.hotkey("command", "d")
    else:
        pyautogui.hotkey("alt", "n")


def close_app_save(filename: str | None = None):
    """
    Save the current document, then close the app.

    Flow:
      1. Ctrl+S (or ⌘+S) to trigger the app's save action.
      2. Wait 0.4s and check whether a "Save As" dialog appeared.
      3. If the dialog is open: type the filename (provided or concept-based
         from the document content, fallback ``untitled_<ts>.txt``) and press
         Enter — the OS saves in the dialog's current directory.
      4. Close the app with Alt+F4 / ⌘+Q.
    """
    save_file()
    time.sleep(0.4)

    if _is_save_as_dialog_open():
        _handle_save_as_dialog(filename)

    time.sleep(0.2)
    close_app()


def close_app_no_save():
    """Chiude l'app scartando modifiche non salvate."""
    close_app()
    _dismiss_save_dialog_dont_save()


def close_window_save(filename: str | None = None):
    """
    Save the current document then close only the current window (Ctrl+W).
    Uses the same Save-As handling as :func:`close_app_save`.
    """
    save_file()
    time.sleep(0.4)

    if _is_save_as_dialog_open():
        _handle_save_as_dialog(filename)

    time.sleep(0.2)
    close_window()


def close_window_no_save():
    close_window()
    _dismiss_save_dialog_dont_save()

def close_window():
    if _OS == "Darwin": pyautogui.hotkey("command", "w")
    else:               pyautogui.hotkey("ctrl", "w")

def full_screen():
    if _OS == "Darwin": pyautogui.hotkey("ctrl", "command", "f")
    else:               pyautogui.press("f11")

def minimize_window():
    if _OS == "Darwin": pyautogui.hotkey("command", "m")
    else:               pyautogui.hotkey("win", "down")

def maximize_window():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to keystroke "f" '
            'using {control down, command down}'],
            capture_output=True)
    elif _OS == "Windows":
        pyautogui.hotkey("win", "up")
    else:
        try:
            subprocess.run(["wmctrl", "-r", ":ACTIVE:", "-b", "add,maximized_vert,maximized_horz"],
                capture_output=True)
        except Exception:
            pyautogui.hotkey("super", "up")

def snap_left():
    if _OS == "Windows":
        pyautogui.hotkey("win", "left")
    elif _OS == "Darwin":
        try:
            subprocess.run(["open", "-a", "Rectangle"], capture_output=True, timeout=1)
        except Exception:
            pass
        pyautogui.hotkey("ctrl", "option", "left")
    else:  # Linux
        try:
            subprocess.run(["wmctrl", "-r", ":ACTIVE:", "-e", "0,0,0,960,1080"],
                capture_output=True)
        except Exception:
            pass

def snap_right():
    if _OS == "Windows":
        pyautogui.hotkey("win", "right")
    elif _OS == "Darwin":
        try:
            subprocess.run(["open", "-a", "Rectangle"], capture_output=True, timeout=1)
        except Exception:
            pass
        pyautogui.hotkey("ctrl", "option", "right")
    else:  # Linux
        try:
            subprocess.run(["wmctrl", "-r", ":ACTIVE:", "-e", "0,960,0,960,1080"],
                capture_output=True)
        except Exception:
            pass

def switch_window():
    if _OS == "Darwin": pyautogui.hotkey("command", "tab")
    else:               pyautogui.hotkey("alt", "tab")

def show_desktop():
    if _OS == "Darwin":   pyautogui.hotkey("fn", "f11")
    elif _OS == "Windows": pyautogui.hotkey("win", "d")
    else:                  pyautogui.hotkey("super", "d")

def open_task_manager():
    if _OS == "Windows":
        pyautogui.hotkey("ctrl", "shift", "esc")
    elif _OS == "Darwin":
        subprocess.Popen(["open", "-a", "Activity Monitor"])
    else:
        for cmd in [["gnome-system-monitor"], ["xfce4-taskmanager"], ["htop"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                break


def focus_search():
    if _OS == "Darwin": pyautogui.hotkey("command", "l")
    else:               pyautogui.hotkey("ctrl", "l")

def pause_video():      pyautogui.press("space")

def refresh_page():
    if _OS == "Darwin": pyautogui.hotkey("command", "r")
    else:               pyautogui.press("f5")

def close_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "w")
    else:               pyautogui.hotkey("ctrl", "w")

def new_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "t")
    else:               pyautogui.hotkey("ctrl", "t")

def next_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "shift", "bracketright")
    else:               pyautogui.hotkey("ctrl", "tab")

def prev_tab():
    if _OS == "Darwin": pyautogui.hotkey("command", "shift", "bracketleft")
    else:               pyautogui.hotkey("ctrl", "shift", "tab")

def go_back():
    if _OS == "Darwin": pyautogui.hotkey("command", "left")
    else:               pyautogui.hotkey("alt", "left")

def go_forward():
    if _OS == "Darwin": pyautogui.hotkey("command", "right")
    else:               pyautogui.hotkey("alt", "right")

def zoom_in():
    if _OS == "Darwin": pyautogui.hotkey("command", "equal")
    else:               pyautogui.hotkey("ctrl", "equal")

def zoom_out():
    if _OS == "Darwin": pyautogui.hotkey("command", "minus")
    else:               pyautogui.hotkey("ctrl", "minus")

def zoom_reset():
    if _OS == "Darwin": pyautogui.hotkey("command", "0")
    else:               pyautogui.hotkey("ctrl", "0")

def find_on_page():
    if _OS == "Darwin": pyautogui.hotkey("command", "f")
    else:               pyautogui.hotkey("ctrl", "f")

def reload_page_n(n: int):
    for _ in range(max(1, n)):
        refresh_page()
        time.sleep(0.8)


def scroll_up(amount: int = 500):    pyautogui.scroll(amount)
def scroll_down(amount: int = 500):  pyautogui.scroll(-amount)

def scroll_top():
    if _OS == "Darwin": pyautogui.hotkey("command", "up")
    else:               pyautogui.hotkey("ctrl", "home")

def scroll_bottom():
    if _OS == "Darwin": pyautogui.hotkey("command", "down")
    else:               pyautogui.hotkey("ctrl", "end")

def page_up():   pyautogui.press("pageup")
def page_down(): pyautogui.press("pagedown")


def copy():
    if _OS == "Darwin": pyautogui.hotkey("command", "c")
    else:               pyautogui.hotkey("ctrl", "c")

def paste():
    if _OS == "Darwin": pyautogui.hotkey("command", "v")
    else:               pyautogui.hotkey("ctrl", "v")

def cut():
    if _OS == "Darwin": pyautogui.hotkey("command", "x")
    else:               pyautogui.hotkey("ctrl", "x")

def undo():
    if _OS == "Darwin": pyautogui.hotkey("command", "z")
    else:               pyautogui.hotkey("ctrl", "z")

def redo():
    if _OS == "Darwin": pyautogui.hotkey("command", "shift", "z")
    else:               pyautogui.hotkey("ctrl", "y")

def select_all():
    if _OS == "Darwin": pyautogui.hotkey("command", "a")
    else:               pyautogui.hotkey("ctrl", "a")

def save_file():
    if _OS == "Darwin": pyautogui.hotkey("command", "s")
    else:               pyautogui.hotkey("ctrl", "s")

def press_enter():   pyautogui.press("enter")
def press_escape():  pyautogui.press("escape")
def press_key(key: str): pyautogui.press(key)

def type_text(text: str, press_enter_after: bool = False):
    if not text:
        return
    if _PYPERCLIP:
        pyperclip.copy(str(text))
        time.sleep(0.15)
        paste()
    else:
        pyautogui.write(str(text), interval=0.03)
    if press_enter_after:
        time.sleep(0.1)
        pyautogui.press("enter")

def take_screenshot():
    if _OS == "Windows":
        pyautogui.hotkey("win", "shift", "s")
    elif _OS == "Darwin":
        pyautogui.hotkey("command", "shift", "3")
    else:
        for cmd in [["scrot"], ["gnome-screenshot"], ["import", "-window", "root", "screenshot.png"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                return
        pyautogui.hotkey("ctrl", "print_screen")

def lock_screen():
    if _OS == "Windows":
        pyautogui.hotkey("win", "l")
    elif _OS == "Darwin":
        subprocess.run(["pmset", "displaysleepnow"], capture_output=True)
    else:
        for cmd in [
            ["gnome-screensaver-command", "-l"],
            ["xdg-screensaver", "lock"],
            ["loginctl", "lock-session"],
        ]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.run(cmd, capture_output=True)
                return

def open_system_settings():
    if _OS == "Windows":
        pyautogui.hotkey("win", "i")
    elif _OS == "Darwin":
        subprocess.Popen(["open", "-a", "System Preferences"])
    else:
        for cmd in [["gnome-control-center"], ["xfce4-settings-manager"], ["kcmshell5"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                return

def open_file_explorer():
    if _OS == "Windows":
        pyautogui.hotkey("win", "e")
    elif _OS == "Darwin":
        subprocess.Popen(["open", str(Path.home())])
    else:
        for cmd in [["nautilus"], ["thunar"], ["dolphin"], ["nemo"]]:
            if subprocess.run(["which", cmd[0]], capture_output=True).returncode == 0:
                subprocess.Popen(cmd)
                return
        subprocess.Popen(["xdg-open", str(Path.home())])

def sleep_display():
    if _OS == "Windows":
        try:
            import ctypes
            ctypes.windll.user32.SendMessageW(0xFFFF, 0x0112, 0xF170, 2)
        except Exception as e:
            print(f"[Settings] sleep_display failed: {e}")
    elif _OS == "Darwin":
        subprocess.run(["pmset", "displaysleepnow"], capture_output=True)
    else:
        subprocess.run(["xset", "dpms", "force", "off"], capture_output=True)

def open_run():
    if _OS == "Windows":
        pyautogui.hotkey("win", "r")

def dark_mode():
    if _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell app "System Events" to tell appearance preferences '
            'to set dark mode to not dark mode'],
            capture_output=True)
    elif _OS == "Windows":
        try:
            import winreg
            key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            current, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.SetValueEx(key, "AppsUseLightTheme", 0, winreg.REG_DWORD, 1 - current)
            winreg.SetValueEx(key, "SystemUsesLightTheme", 0, winreg.REG_DWORD, 1 - current)
            winreg.CloseKey(key)
        except Exception as e:
            print(f"[Settings] dark_mode registry failed: {e}")
    else:
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                capture_output=True, text=True
            )
            current = result.stdout.strip()
            new_scheme = "'default'" if "dark" in current else "'prefer-dark'"
            subprocess.run(
                ["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", new_scheme],
                capture_output=True
            )
        except Exception as e:
            print(f"[Settings] dark_mode Linux failed: {e}")

def toggle_wifi():
    if _OS == "Darwin":
        iface = _get_macos_wifi_interface()
        result = subprocess.run(
            ["networksetup", "-getairportpower", iface],
            capture_output=True, text=True
        )
        state = "off" if "On" in result.stdout else "on"
        subprocess.run(["networksetup", "-setairportpower", iface, state],
            capture_output=True)
    elif _OS == "Windows":
        try:
            subprocess.run(
                ["powershell", "-Command",
                 "$adapter = Get-NetAdapter | Where-Object {$_.PhysicalMediaType -eq 'Native 802.11'};"
                 "if ($adapter.Status -eq 'Up') { Disable-NetAdapter -Name $adapter.Name -Confirm:$false }"
                 "else { Enable-NetAdapter -Name $adapter.Name -Confirm:$false }"],
                capture_output=True, timeout=10, **_WIN_HIDE
            )
        except Exception as e:
            print(f"[Settings] toggle_wifi Windows failed: {e}")
    else:
        try:
            result = subprocess.run(["nmcli", "radio", "wifi"], capture_output=True, text=True)
            state  = "off" if "enabled" in result.stdout else "on"
            subprocess.run(["nmcli", "radio", "wifi", state], capture_output=True)
        except Exception as e:
            print(f"[Settings] toggle_wifi Linux failed: {e}")

def restart_computer():
    if _OS == "Windows":
        subprocess.run(["shutdown", "/r", "/t", "10"], capture_output=True, **_WIN_HIDE)
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to restart'],
            capture_output=True)
    else:
        subprocess.run(["systemctl", "reboot"], capture_output=True)

def shutdown_computer():
    if _OS == "Windows":
        subprocess.run(["shutdown", "/s", "/t", "10"], capture_output=True)
    elif _OS == "Darwin":
        subprocess.run(["osascript", "-e",
            'tell application "System Events" to shut down'],
            capture_output=True)
    else:
        subprocess.run(["systemctl", "poweroff"], capture_output=True)

ACTION_MAP: dict[str, callable] = {
    "volume_up":           volume_up,
    "volume_down":         volume_down,
    "mute":                volume_mute,
    "unmute":              volume_mute,
    "toggle_mute":         volume_mute,
    "brightness_up":       brightness_up,
    "brightness_down":     brightness_down,
    "sleep_display":       sleep_display,
    "screen_off":          sleep_display,
    "pause_video":         pause_video,
    "play_pause":          pause_video,
    "close_app":           close_app,
    "close_window":        close_window,
    "full_screen":         full_screen,
    "fullscreen":          full_screen,
    "minimize":            minimize_window,
    "maximize":            maximize_window,
    "snap_left":           snap_left,
    "snap_right":          snap_right,
    "switch_window":       switch_window,
    "show_desktop":        show_desktop,
    "task_manager":        open_task_manager,
    "focus_search":        focus_search,
    "refresh_page":        refresh_page,
    "reload":              refresh_page,
    "close_tab":           close_tab,
    "new_tab":              new_tab,
    "next_tab":             next_tab,
    "prev_tab":             prev_tab,
    "go_back":             go_back,
    "go_forward":          go_forward,
    "zoom_in":             zoom_in,
    "zoom_out":            zoom_out,
    "zoom_reset":          zoom_reset,
    "find_on_page":        find_on_page,
    "scroll_up":           scroll_up,
    "scroll_down":         scroll_down,
    "scroll_top":          scroll_top,
    "scroll_bottom":       scroll_bottom,
    "page_up":             page_up,
    "page_down":           page_down,
    "copy":                copy,
    "paste":               paste,
    "cut":                 cut,
    "undo":                undo,
    "redo":                redo,
    "select_all":          select_all,
    "save":                save_file,
    "enter":               press_enter,
    "escape":              press_escape,
    "screenshot":          take_screenshot,
    "lock_screen":         lock_screen,
    "open_settings":       open_system_settings,
    "file_explorer":       open_file_explorer,
    "open_run":            open_run,
    "dark_mode":           dark_mode,
    "toggle_wifi":         toggle_wifi,
    "restart":             restart_computer,
    "shutdown":            shutdown_computer,
}

_DANGEROUS_ACTIONS = {"restart", "shutdown"}
_CLOSE_ACTIONS     = {"close_app", "close_window"}
_YES = {"yes", "y", "true", "1", "si", "sì", "salva", "save"}
_NO  = {"no", "n", "false", "0", "non_salvare", "dont_save", "skip", "discard"}


# --------------------------------------------------------------------------- #
#  Tool schema                                                                 #
# --------------------------------------------------------------------------- #
# JSON-Schema style declaration for LLM tool calling. ``filename`` is an
# optional string that the model can supply when it already knows how the
# document should be named on disk (e.g. the user said "salva come lettera").
COMPUTER_SETTINGS_TOOL_SCHEMA = {
    "name": "computer_settings",
    "description": (
        "Control system settings and app windows (volume, brightness, "
        "close app/window with or without saving, tabs, scrolling, etc.)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": (
                    "The action to perform. Examples: 'volume_up', "
                    "'close_app', 'close_window', 'refresh_page'."
                ),
            },
            "description": {
                "type": "string",
                "description": (
                    "Free-form user request when no explicit action is "
                    "known; will be resolved via intent detection."
                ),
            },
            "value": {
                "description": "Optional value for parameterised actions."
            },
            "save_choice": {
                "type": "string",
                "enum": ["yes", "no", "si", "sì", "salva", "save",
                         "non_salvare", "dont_save", "discard"],
                "description": (
                    "Only for close_app / close_window: whether to save "
                    "before closing."
                ),
            },
            "filename": {
                "type": "string",
                "description": (
                    "Filename to type into the 'Save As' dialog when it "
                    "pops up during close_app / close_window. Choose a "
                    "concept-based name from the document content (e.g. "
                    "'lettera.txt' for a letter, 'poesia_amore.txt' for a "
                    "poem, 'lista_spesa.txt' for a shopping list). Do NOT "
                    "include any path — just the bare filename. If "
                    "omitted, fallback is 'untitled_<timestamp>.txt'."
                ),
            },
            "confirmed": {
                "type": "string",
                "description": (
                    "Set to 'yes' to confirm destructive actions like "
                    "restart or shutdown."
                ),
            },
        },
        "required": ["action"],
    },
}



def _detect_action(description: str) -> dict:

    from google import genai as _genai
    _client = _genai.Client(api_key=_get_api_key())

    available = ", ".join(sorted(ACTION_MAP.keys())) + \
                ", volume_set, type_text, press_key, reload_n"

    prompt = f"""You are an intent detector for a computer control assistant.

The user issued a command (possibly in any language): "{description}"

Available actions: {available}

Return ONLY a valid JSON object:
{{"action": "action_name", "value": null_or_value}}

Rules:
- Pick the single best matching action from the available list.
- For volume_set: value is an integer 0-100.
- For type_text: value is the exact text to type.
- For press_key: value is the key name (e.g. "f5", "tab", "enter").
- For reload_n: value is an integer (number of times to reload).
- If no clear match, pick the closest action.
- Return ONLY the JSON, no explanation, no markdown."""

    try:
        resp = _client.models.generate_content(model="gemini-2.5-flash-lite", contents=prompt)
        text = re.sub(r"```(?:json)?", "", resp.text).strip().rstrip("`").strip()
        return json.loads(text)
    except Exception as e:
        print(f"[Settings] Intent detection failed: {e}")
        return {"action": description.lower().replace(" ", "_"), "value": None}

def computer_settings(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    if not _PYAUTOGUI:
        return "pyautogui is not installed. Run: pip install pyautogui"

    params      = parameters or {}
    raw_action  = params.get("action", "").strip()
    description = params.get("description", "").strip()
    value       = params.get("value", None)
    filename    = params.get("filename")
    if isinstance(filename, str):
        filename = filename.strip() or None

    if not raw_action and description:
        detected   = _detect_action(description)
        raw_action = detected.get("action", "")
        if value is None:
            value = detected.get("value")

    action = raw_action.lower().strip().replace(" ", "_").replace("-", "_")

    if not action:
        return "No action could be determined."

    print(f"[Settings] Action: {action}  Value: {value}  OS: {_OS}")
    if player:
        player.write_log(f"[Settings] {action}")

    if action in _DANGEROUS_ACTIONS:
        confirmed = str(params.get("confirmed", "")).lower()
        if confirmed not in ("yes", "true", "1", "confirm"):
            return (
                f"This will {action} the computer. "
                f"Please confirm by calling again with confirmed=yes."
            )

    if action in _CLOSE_ACTIONS:
        raw_choice = str(
            params.get("save_choice")
            or params.get("save_before_close")
            or params.get("save")
            or ""
        ).strip().lower().replace(" ", "_")

        # Target app: which application the user actually asked to close.
        # Accept several parameter names the LLM might invent.
        target_app = (
            params.get("target_app")
            or params.get("app")
            or params.get("app_name")
            or params.get("target")
            or params.get("window")
            or ""
        )
        if isinstance(target_app, str):
            target_app = target_app.strip()
        else:
            target_app = ""

        # Some models put the app name in `description` when action is
        # already set. Fall back to it, but only if it looks like a plain
        # app name (short, no spaces / verbs) — otherwise it's a free-form
        # command that we shouldn't try to resolve to a window.
        if not target_app:
            desc = (params.get("description") or "").strip()
            if desc and len(desc) <= 40 and " " not in desc.strip("_-"):
                target_app = desc

        target_title = ""
        if target_app:
            win = _find_window_for_app(target_app)
            if win is None:
                # Couldn't locate the requested app. Tell the model so it
                # can inform the user instead of nuking whatever is in
                # focus (which was the whole bug).
                return (
                    f"APP_NOT_FOUND: no open window found for '{target_app}'. "
                    f"Ask the user to open it first, or specify a different app."
                )
            # Focus the target window BEFORE we send Alt+F4 / Ctrl+W.
            _focus_window(win)
            target_title = (win.title or "").lower()

        is_editor = _active_window_is_editor(target_title or None)

        # Guard rail: if the (target or focused) app is NOT a real
        # document editor (assistant's own UI, browser, media player,
        # terminal, …) ignore any save_choice the model might have sent
        # and just close cleanly.
        if not is_editor:
            if action == "close_window":
                close_window()
                return (
                    f"CLOSED: closed the {target_app or 'current'} window "
                    f"(non-editor, no save prompt)."
                )
            close_app()
            return (
                f"CLOSED: closed {target_app or 'the current app'} "
                f"(non-editor, no save prompt)."
            )

        # From here on we know the target window looks like an editor.
        if raw_choice in _YES:
            if action == "close_window":
                close_window_save(filename)
                return "SAVED_AND_CLOSED: saved (Ctrl+S) then closed the window."
            close_app_save(filename)
            return "SAVED_AND_CLOSED: saved (Ctrl+S) then closed the app."

        if raw_choice in _NO:
            if action == "close_window":
                close_window_no_save()
                return "CLOSED_WITHOUT_SAVE: closed the window discarding changes."
            close_app_no_save()
            return "CLOSED_WITHOUT_SAVE: closed the app discarding changes."

        return (
            "ASK_USER_SAVE_BEFORE_CLOSE: Before I close, do you want me to save the file? "
            "Reply 'sì' to save or 'no' to close without saving. "
            f"Then re-call computer_settings with action='{action}' and save_choice='yes' or 'no'."
        )

    if action == "volume_set":
        try:
            volume_set(int(value or 50))
            return f"Volume set to {value}%."
        except Exception as e:
            return f"Could not set volume: {e}"

    if action in ("type_text", "write_on_screen", "type", "write"):
        text = str(value or params.get("text", "")).strip()
        if not text:
            return "No text provided to type."
        enter_after = str(params.get("press_enter", "false")).lower() in ("true", "1", "yes")
        type_text(text, press_enter_after=enter_after)
        return f"Typed: {text[:80]}"

    if action == "press_key":
        key = str(value or params.get("key", "")).strip()
        if not key:
            return "No key specified."
        press_key(key)
        return f"Pressed: {key}"

    if action in ("reload_n", "refresh_n", "reload_page_n"):
        try:
            reload_page_n(int(value or 1))
            return f"Reloaded {value or 1} time(s)."
        except Exception as e:
            return f"Reload failed: {e}"

    if action == "scroll_up":
        scroll_up(int(value or 500))
        return "Scrolled up."

    if action == "scroll_down":
        scroll_down(int(value or 500))
        return "Scrolled down."

    func = ACTION_MAP.get(action)
    if not func:
        return f"Unknown action: '{raw_action}'."

    try:
        func()
        return f"Done: {action}."
    except Exception as e:
        print(f"[Settings] Action failed ({action}): {e}")
        return f"Action failed ({action}): {e}"

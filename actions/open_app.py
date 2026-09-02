import os
import time
import platform
import shutil
import subprocess
import ctypes
from ctypes import wintypes

# --- WhatsApp HUD interception --------------------------------------------
# Quando l'utente dice "Jarvis apri whatsapp" o "Jarvis tendina whatsapp",
# NON aprire l'app desktop di WhatsApp: apri la TENDINA HUD (slide-in da
# destra) che carica WhatsApp Web in un webview.
try:
    from actions.messaging_panel import open_messaging_panel as _open_wa_panel
except Exception:  # pragma: no cover
    _open_wa_panel = None


def _is_whatsapp_request(raw: str) -> bool:
    if not raw:
        return False
    k = raw.lower().strip()
    # Rimuovi parole tipo "tendina", "hud", "pannello", "apri"
    for w in ("tendina", "pannello", "hud", "apri", "open", "mostra", "la", "il", "di"):
        k = k.replace(w, " ")
    k = " ".join(k.split())
    return k in {"whatsapp", "wa", "whats app", "whatapp"} or "whatsapp" in k


_SYSTEM = platform.system()


# ============================================================
# APP ALIASES
# ============================================================

_APP_ALIASES: dict[str, dict[str, str]] = {

    "chrome": {
        "Windows": "chrome",
        "Darwin": "Google Chrome",
        "Linux": "google-chrome",
    },

    "google chrome": {
        "Windows": "chrome",
        "Darwin": "Google Chrome",
        "Linux": "google-chrome",
    },

    "firefox": {
        "Windows": "firefox",
        "Darwin": "Firefox",
        "Linux": "firefox",
    },

    "edge": {
        "Windows": "msedge",
        "Darwin": "Microsoft Edge",
        "Linux": "microsoft-edge",
    },

    "brave": {
        "Windows": "brave",
        "Darwin": "Brave Browser",
        "Linux": "brave-browser",
    },

    "safari": {
        "Windows": "msedge",
        "Darwin": "Safari",
        "Linux": "firefox",
    },

    "opera": {
        "Windows": "opera",
        "Darwin": "Opera",
        "Linux": "opera",
    },

    "whatsapp": {
        "Windows": "WhatsApp",
        "Darwin": "WhatsApp",
        "Linux": "whatsapp",
    },

    "telegram": {
        "Windows": "Telegram",
        "Darwin": "Telegram",
        "Linux": "telegram",
    },

    "discord": {
        "Windows": "Discord",
        "Darwin": "Discord",
        "Linux": "discord",
    },

    "slack": {
        "Windows": "Slack",
        "Darwin": "Slack",
        "Linux": "slack",
    },

    "zoom": {
        "Windows": "Zoom",
        "Darwin": "zoom.us",
        "Linux": "zoom",
    },

    "teams": {
        "Windows": "msteams",
        "Darwin": "Microsoft Teams",
        "Linux": "teams",
    },

    "microsoft teams": {
        "Windows": "msteams",
        "Darwin": "Microsoft Teams",
        "Linux": "teams",
    },

    "skype": {
        "Windows": "skype",
        "Darwin": "Skype",
        "Linux": "skype",
    },

    "signal": {
        "Windows": "signal",
        "Darwin": "Signal",
        "Linux": "signal",
    },

    "spotify": {
        "Windows": "Spotify",
        "Darwin": "Spotify",
        "Linux": "spotify",
    },

    "vlc": {
        "Windows": "vlc",
        "Darwin": "VLC",
        "Linux": "vlc",
    },

    "netflix": {
        "Windows": "Netflix",
        "Darwin": "Netflix",
        "Linux": "firefox",
    },

    "vscode": {
        "Windows": "code",
        "Darwin": "Visual Studio Code",
        "Linux": "code",
    },

    "visual studio code": {
        "Windows": "code",
        "Darwin": "Visual Studio Code",
        "Linux": "code",
    },

    "code": {
        "Windows": "code",
        "Darwin": "Visual Studio Code",
        "Linux": "code",
    },

    "terminal": {
        "Windows": "wt",
        "Darwin": "Terminal",
        "Linux": "x-terminal-emulator",
    },

    "windows terminal": {
        "Windows": "wt",
        "Darwin": "Terminal",
        "Linux": "x-terminal-emulator",
    },

    "cmd": {
        "Windows": "cmd.exe",
        "Darwin": "Terminal",
        "Linux": "bash",
    },

    "powershell": {
        "Windows": "powershell.exe",
        "Darwin": "Terminal",
        "Linux": "bash",
    },

    "postman": {
        "Windows": "Postman",
        "Darwin": "Postman",
        "Linux": "postman",
    },

    "git": {
        "Windows": "git-bash",
        "Darwin": "Terminal",
        "Linux": "bash",
    },

    "figma": {
        "Windows": "Figma",
        "Darwin": "Figma",
        "Linux": "figma",
    },

    "blender": {
        "Windows": "blender",
        "Darwin": "Blender",
        "Linux": "blender",
    },

    "word": {
        "Windows": "winword",
        "Darwin": "Microsoft Word",
        "Linux": "libreoffice --writer",
    },

    "microsoft word": {
        "Windows": "winword",
        "Darwin": "Microsoft Word",
        "Linux": "libreoffice --writer",
    },

    "excel": {
        "Windows": "excel",
        "Darwin": "Microsoft Excel",
        "Linux": "libreoffice --calc",
    },

    "microsoft excel": {
        "Windows": "excel",
        "Darwin": "Microsoft Excel",
        "Linux": "libreoffice --calc",
    },

    "powerpoint": {
        "Windows": "powerpnt",
        "Darwin": "Microsoft PowerPoint",
        "Linux": "libreoffice --impress",
    },

    "microsoft powerpoint": {
        "Windows": "powerpnt",
        "Darwin": "Microsoft PowerPoint",
        "Linux": "libreoffice --impress",
    },

    "libreoffice": {
        "Windows": "soffice",
        "Darwin": "LibreOffice",
        "Linux": "libreoffice",
    },

    "notepad": {
        "Windows": "notepad.exe",
        "Darwin": "TextEdit",
        "Linux": "gedit",
    },

    "textedit": {
        "Windows": "notepad.exe",
        "Darwin": "TextEdit",
        "Linux": "gedit",
    },

    "explorer": {
        "Windows": "explorer.exe",
        "Darwin": "Finder",
        "Linux": "nautilus",
    },

    "file explorer": {
        "Windows": "explorer.exe",
        "Darwin": "Finder",
        "Linux": "nautilus",
    },

    "finder": {
        "Windows": "explorer.exe",
        "Darwin": "Finder",
        "Linux": "nautilus",
    },

    "task manager": {
        "Windows": "taskmgr.exe",
        "Darwin": "Activity Monitor",
        "Linux": "gnome-system-monitor",
    },

    "settings": {
        "Windows": "ms-settings:",
        "Darwin": "System Preferences",
        "Linux": "gnome-control-center",
    },

    "calculator": {
        "Windows": "calc.exe",
        "Darwin": "Calculator",
        "Linux": "gnome-calculator",
    },

    "paint": {
        "Windows": "mspaint.exe",
        "Darwin": "Preview",
        "Linux": "gimp",
    },

    "instagram": {
        "Windows": "Instagram",
        "Darwin": "Instagram",
        "Linux": "firefox",
    },

    "tiktok": {
        "Windows": "TikTok",
        "Darwin": "TikTok",
        "Linux": "firefox",
    },

    "notion": {
        "Windows": "Notion",
        "Darwin": "Notion",
        "Linux": "notion",
    },

    "obsidian": {
        "Windows": "Obsidian",
        "Darwin": "Obsidian",
        "Linux": "obsidian",
    },

    "capcut": {
        "Windows": "CapCut",
        "Darwin": "CapCut",
        "Linux": "capcut",
    },

    "steam": {
        "Windows": "steam",
        "Darwin": "Steam",
        "Linux": "steam",
    },

    "epic": {
        "Windows": "EpicGamesLauncher",
        "Darwin": "Epic Games Launcher",
        "Linux": "legendary",
    },

    "epic games": {
        "Windows": "EpicGamesLauncher",
        "Darwin": "Epic Games Launcher",
        "Linux": "legendary",
    },
}


# ============================================================
# NORMALIZZAZIONE
# ============================================================

def _normalize(raw: str) -> str:

    if not raw:
        return ""

    key = raw.lower().strip()

    # Match esatto
    if key in _APP_ALIASES:
        return _APP_ALIASES[key].get(
            _SYSTEM,
            raw
        )

    # Match parziale
    for alias_key, os_map in _APP_ALIASES.items():

        if (
            alias_key in key
            or key in alias_key
        ):
            return os_map.get(
                _SYSTEM,
                raw
            )

    return raw


# ============================================================
# WINDOWS - SHELL EXECUTE
# ============================================================

def _windows_shell_execute(
    target: str,
    parameters: str = "",
) -> bool:
    """
    Avvia un'app tramite ShellExecuteW.

    Non apre CMD.
    Non apre PowerShell.
    Non apre la ricerca di Windows.
    """

    try:

        shell32 = ctypes.windll.shell32

        result = shell32.ShellExecuteW(
            None,
            "open",
            target,
            parameters if parameters else None,
            None,
            1,
        )

        # ShellExecute ritorna > 32 in caso di successo
        return result > 32

    except Exception as e:

        print(
            f"[open_app] ShellExecute error: {e}"
        )

        return False


# ============================================================
# WINDOWS - START MENU APP DISCOVERY
# ============================================================

def _windows_find_start_app(
    app_name: str,
) -> str | None:
    """
    Cerca un'app registrata nel menu Start.

    Usa Get-StartApps in background.

    NON apre finestre.
    NON modifica il focus.
    """

    powershell = shutil.which(
        "powershell.exe"
    )

    if not powershell:
        return None

    # Stringa passata a PowerShell in modo sicuro.
    escaped = app_name.replace(
        "'",
        "''"
    )

    command = (
        "$ErrorActionPreference='SilentlyContinue'; "
        f"$apps = Get-StartApps | "
        f"Where-Object {{ $_.Name -like '*{escaped}*' }}; "
        "if ($apps) { "
        "$apps | Select-Object -First 1 -ExpandProperty AppID "
        "}"
    )

    try:

        result = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0x08000000,
            ),
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=5,
        )

        app_id = result.stdout.strip()

        if app_id:
            return app_id

    except (
        OSError,
        subprocess.SubprocessError,
    ) as e:

        print(
            f"[open_app] Start app lookup error: {e}"
        )

    return None


# ============================================================
# WINDOWS - APP FOLDER LAUNCH
# ============================================================

def _windows_launch_start_app(
    app_id: str,
) -> bool:
    """
    Avvia una Windows Store / Start Menu app
    tramite shell:AppsFolder.

    Non usa la barra di ricerca.
    """

    if not app_id:
        return False

    try:

        shell_path = (
            "shell:AppsFolder\\"
            + app_id
        )

        return _windows_shell_execute(
            shell_path
        )

    except Exception:

        return False


# ============================================================
# WINDOWS
# ============================================================

def _launch_windows(
    app_name: str,
) -> bool:

    app_name = app_name.strip()

    if not app_name:
        return False

    # --------------------------------------------------------
    # 1. URI Windows
    # --------------------------------------------------------

    if (
        ":" in app_name
        and not app_name.lower().endswith(
            (
                ".exe",
                ".bat",
                ".cmd",
            )
        )
    ):

        if _windows_shell_execute(
            app_name
        ):

            time.sleep(0.5)
            return True

    # --------------------------------------------------------
    # 2. Percorso completo
    # --------------------------------------------------------

    expanded = os.path.expandvars(
        os.path.expanduser(
            app_name
        )
    )

    if os.path.isfile(expanded):

        if _windows_shell_execute(
            expanded
        ):

            time.sleep(0.5)
            return True

    # --------------------------------------------------------
    # 3. PATH
    # --------------------------------------------------------

    candidates = [
        app_name,
        app_name + ".exe",
    ]

    for candidate in candidates:

        executable = shutil.which(
            candidate
        )

        if executable:

            try:

                subprocess.Popen(
                    [executable],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(
                        subprocess,
                        "CREATE_NO_WINDOW",
                        0x08000000,
                    ),
                    close_fds=True,
                )

                time.sleep(0.5)

                return True

            except (
                OSError,
                subprocess.SubprocessError,
            ):
                pass

    # --------------------------------------------------------
    # 4. Start Menu / Microsoft Store
    # --------------------------------------------------------

    app_id = _windows_find_start_app(
        app_name
    )

    if app_id:

        print(
            f"[open_app] Start App found: "
            f"{app_id}"
        )

        if _windows_launch_start_app(
            app_id
        ):

            time.sleep(0.7)
            return True

    # --------------------------------------------------------
    # 5. ShellExecute diretto
    #
    # Può risolvere alcuni App Execution Alias
    # --------------------------------------------------------

    if _windows_shell_execute(
        app_name
    ):

        time.sleep(0.7)
        return True

    return False


# ============================================================
# MACOS
# ============================================================

def _launch_macos(
    app_name: str,
) -> bool:

    app_name = app_name.strip()

    if not app_name:
        return False

    # --------------------------------------------------------
    # open -a
    # --------------------------------------------------------

    try:

        result = subprocess.run(
            [
                "open",
                "-a",
                app_name,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )

        if result.returncode == 0:

            time.sleep(0.7)
            return True

    except (
        OSError,
        subprocess.SubprocessError,
    ):
        pass

    # --------------------------------------------------------
    # .app
    # --------------------------------------------------------

    try:

        result = subprocess.run(
            [
                "open",
                "-a",
                f"{app_name}.app",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
        )

        if result.returncode == 0:

            time.sleep(0.7)
            return True

    except (
        OSError,
        subprocess.SubprocessError,
    ):
        pass

    # --------------------------------------------------------
    # PATH
    # --------------------------------------------------------

    binary = (
        shutil.which(app_name)
        or shutil.which(
            app_name.lower()
        )
    )

    if binary:

        try:

            subprocess.Popen(
                [binary],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )

            time.sleep(0.7)
            return True

        except (
            OSError,
            subprocess.SubprocessError,
        ):
            pass

    return False


# ============================================================
# LINUX
# ============================================================

_LINUX_TERMINAL_FALLBACKS = [
    "x-terminal-emulator",
    "gnome-terminal",
    "konsole",
    "xfce4-terminal",
    "xterm",
    "lxterminal",
    "mate-terminal",
    "tilix",
    "alacritty",
    "kitty",
]


def _launch_linux(
    app_name: str,
) -> bool:

    app_name = app_name.strip()

    if not app_name:
        return False

    # --------------------------------------------------------
    # Terminal
    # --------------------------------------------------------

    if app_name in (
        "x-terminal-emulator",
        "gnome-terminal",
        "terminal",
    ):

        for terminal in _LINUX_TERMINAL_FALLBACKS:

            if shutil.which(terminal):

                try:

                    subprocess.Popen(
                        [terminal],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        close_fds=True,
                    )

                    time.sleep(0.7)

                    return True

                except (
                    OSError,
                    subprocess.SubprocessError,
                ):
                    continue

    # --------------------------------------------------------
    # PATH
    # --------------------------------------------------------

    candidates = [
        app_name,
        app_name.lower(),
        app_name.lower().replace(
            " ",
            "-"
        ),
        app_name.lower().replace(
            " ",
            "_"
        ),
    ]

    for candidate in candidates:

        binary = shutil.which(
            candidate
        )

        if binary:

            try:

                subprocess.Popen(
                    [binary],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    close_fds=True,
                )

                time.sleep(0.7)

                return True

            except (
                OSError,
                subprocess.SubprocessError,
            ):
                pass

    # --------------------------------------------------------
    # Desktop application
    # --------------------------------------------------------

    if shutil.which("gtk-launch"):

        desktop_names = [
            app_name.lower(),
            app_name.lower().replace(
                " ",
                "-"
            ),
            app_name.lower().replace(
                " ",
                ""
            ),
        ]

        for desktop_name in desktop_names:

            try:

                result = subprocess.run(
                    [
                        "gtk-launch",
                        desktop_name,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )

                if result.returncode == 0:

                    time.sleep(0.7)
                    return True

            except (
                OSError,
                subprocess.SubprocessError,
            ):
                pass

    # --------------------------------------------------------
    # xdg-open
    # --------------------------------------------------------

    if shutil.which("xdg-open"):

        try:

            result = subprocess.run(
                [
                    "xdg-open",
                    app_name,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )

            if result.returncode == 0:

                time.sleep(0.7)
                return True

        except (
            OSError,
            subprocess.SubprocessError,
        ):
            pass

    return False


# ============================================================
# OS LAUNCHERS
# ============================================================

_OS_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin": _launch_macos,
    "Linux": _launch_linux,
}


# ============================================================
# PUBLIC FUNCTION
# ============================================================

def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:

    parameters = parameters or {}

    raw_name = parameters.get(
        "app_name",
        ""
    )

    if raw_name is None:
        raw_name = ""

    app_name = str(
        raw_name
    ).strip()

    if not app_name:
        return "No application name provided."

    # ------------------------------------------------------------------
    # WhatsApp -> TENDINA HUD (slide-in da destra con WhatsApp Web)
    # ------------------------------------------------------------------
    if _is_whatsapp_request(app_name) and _open_wa_panel is not None:
        try:
            msg = _open_wa_panel("whatsapp") or "Tendina WhatsApp aperta, signore."
            if player:
                try:
                    player.write_log(f"[open_app] whatsapp -> tendina HUD")
                except Exception:
                    pass
            return msg
        except Exception as e:
            print(f"[open_app] tendina whatsapp fallback -> desktop: {e}")

    launcher = _OS_LAUNCHERS.get(
        _SYSTEM
    )

    if launcher is None:

        return (
            f"Unsupported operating system: "
            f"{_SYSTEM}"
        )

    normalized = _normalize(
        app_name
    )

    print(
        f"[open_app] "
        f"Launching '{app_name}' "
        f"→ '{normalized}' "
        f"({_SYSTEM})"
    )

    # --------------------------------------------------------
    # JARVIS LOG
    # --------------------------------------------------------

    if player:

        try:

            player.write_log(
                f"[open_app] {app_name}"
            )

        except Exception as e:

            print(
                f"[open_app] Log error: {e}"
            )

    # --------------------------------------------------------
    # Launch
    # --------------------------------------------------------

    try:

        success = launcher(
            normalized
        )

        # Se l'alias non funziona,
        # prova anche il nome originale.
        if not success and (
            normalized.lower()
            != app_name.lower()
        ):

            success = launcher(
                app_name
            )

        if success:

            return (
                f"Opened {app_name}."
            )

        return (
            f"Could not launch "
            f"'{app_name}'. "
            f"The application may not "
            f"be installed or may have "
            f"a different registered name."
        )

    except Exception as e:

        print(
            f"[open_app] Error: {e}"
        )

        return (
            f"Failed to open "
            f"{app_name}: {e}"
        )

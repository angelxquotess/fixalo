"""actions/shortcut_creator.py

Sistema di SCORCIATOIE per JARVIS.

L'utente puo' dire:
    "jarvis crea scorciatoia"
        -> nome:        "ricerca tonno"
        -> cosa fare:   "ricerca tonno fresco"
    "jarvis crea scorciatoia"
        -> nome:        "apri chatgpt"
        -> cosa fare:   "apri chatgpt"
    "jarvis crea scorciatoia"
        -> nome:        "avvia gioco"
        -> cosa fare:   "avvia un file C:/Games/MyGame.exe"

Per ogni scorciatoia viene generato un file Python autonomo dentro la
cartella `scorciatoie/<slug>.py` contenente la funzione `run()` che
esegue il comando.

Inoltre viene mantenuto un registro JSON in `scorciatoie/_index.json`
con tutte le scorciatoie disponibili (per consultazione rapida e per il
comando "jarvis esegui scorciatoia <nome>").
"""

from __future__ import annotations

import json
import os
import re
import sys
import platform
import subprocess
import webbrowser
import urllib.parse
from pathlib import Path
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------
def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


SHORTCUTS_DIR = _base_dir() / "scorciatoie"
INDEX_FILE    = SHORTCUTS_DIR / "_index.json"


def _slugify(name: str) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9_\- ]+", "", s)
    s = re.sub(r"[\s\-]+", "_", s)
    return s or "scorciatoia"


# ---------------------------------------------------------------
# Desktop physical shortcut helpers (.lnk / .desktop / .command)
# ---------------------------------------------------------------
def _desktop_dir() -> Path:
    """Return the OS-specific Desktop folder."""
    # Windows / Linux / macOS all usually have ~/Desktop
    p = Path.home() / "Desktop"
    if p.exists():
        return p
    # Fallback: home
    return Path.home()


def _create_windows_lnk(shortcut_path: Path, target: str,
                        arguments: str = "",
                        working_dir: str = "",
                        icon: str = "",
                        description: str = "") -> bool:
    """Create a real .lnk file on Windows using COM (pywin32) or PowerShell."""
    # Try pywin32 first (no console window, silent)
    try:
        import pythoncom  # type: ignore
        from win32com.client import Dispatch  # type: ignore

        shell = Dispatch("WScript.Shell")
        sc = shell.CreateShortCut(str(shortcut_path))
        sc.Targetpath = target
        if arguments:
            sc.Arguments = arguments
        if working_dir:
            sc.WorkingDirectory = working_dir
        if icon:
            sc.IconLocation = icon
        if description:
            sc.Description = description
        sc.save()
        return True
    except Exception:
        pass

    # PowerShell fallback (works on plain Windows with no extra deps)
    try:
        ps_target   = target.replace("'", "''")
        ps_args     = arguments.replace("'", "''")
        ps_wd       = working_dir.replace("'", "''")
        ps_icon     = icon.replace("'", "''")
        ps_desc     = description.replace("'", "''")
        ps_lnk      = str(shortcut_path).replace("'", "''")

        script = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$s = $ws.CreateShortcut('{ps_lnk}'); "
            f"$s.TargetPath = '{ps_target}'; "
        )
        if arguments:
            script += f"$s.Arguments = '{ps_args}'; "
        if working_dir:
            script += f"$s.WorkingDirectory = '{ps_wd}'; "
        if icon:
            script += f"$s.IconLocation = '{ps_icon}'; "
        if description:
            script += f"$s.Description = '{ps_desc}'; "
        script += "$s.Save()"

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=10, creationflags=creationflags,
        )
        return shortcut_path.exists()
    except Exception:
        return False


def _create_linux_desktop_file(shortcut_path: Path, exec_cmd: str,
                               name: str, icon: str = "",
                               comment: str = "") -> bool:
    try:
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Version=1.0\n"
            f"Name={name}\n"
            f"Comment={comment or 'Scorciatoia creata da JARVIS'}\n"
            f"Exec={exec_cmd}\n"
        )
        if icon:
            content += f"Icon={icon}\n"
        content += "Terminal=false\nCategories=Utility;\n"
        shortcut_path.write_text(content, encoding="utf-8")
        try:
            shortcut_path.chmod(0o755)
        except Exception:
            pass
        return True
    except Exception:
        return False


def _create_mac_command_file(shortcut_path: Path, exec_cmd: str) -> bool:
    try:
        content = "#!/bin/bash\n" + exec_cmd + "\n"
        shortcut_path.write_text(content, encoding="utf-8")
        try:
            shortcut_path.chmod(0o755)
        except Exception:
            pass
        return True
    except Exception:
        return False


def _build_exec_command_for_shortcut(slug: str) -> tuple[str, str, str]:
    """Return (target, arguments, working_dir) that runs `run_shortcut(<slug>)`.

    We invoke the same Python interpreter that Jarvis is running under and
    execute the generated scorciatoie/<slug>.py file directly, so the
    physical shortcut works even when Jarvis is closed.
    """
    py = sys.executable or "python"
    script_path = str((SHORTCUTS_DIR / f"{slug}.py").resolve())
    return py, f'"{script_path}"', str(SHORTCUTS_DIR.resolve())


def create_desktop_shortcut(parameters: Optional[dict] = None,
                            response=None, player=None,
                            session_memory=None) -> str:
    """Crea una scorciatoia FISICA sul desktop dell'utente.

    Se la scorciatoia logica (slug) non esiste ancora, viene creata al volo
    usando `parameters['action']` come descrizione di cosa deve fare.

    parameters:
        name    : nome visibile della scorciatoia sul desktop
        slug    : (opzionale) slug esistente da "collegare"
        action  : (opzionale) se non esiste ancora una scorciatoia con quel
                  nome/slug, viene creata usando questo testo
        icon    : (opzionale) percorso a un file .ico / .png
    """
    params = parameters or {}
    name    = (params.get("name") or "").strip()
    slug_in = (params.get("slug") or "").strip()
    action_text = (params.get("action") or params.get("do") or "").strip()
    icon    = (params.get("icon") or "").strip()

    if not name and not slug_in:
        return "Capo, dimmi il nome della scorciatoia da mettere sul desktop."

    _ensure_dirs()
    idx = _load_index()
    items = idx.get("shortcuts", {})

    # Trova o crea la scorciatoia logica
    slug = _slugify(slug_in or name)
    if slug not in items:
        # Se non esiste, prova match parziale per nome
        for s, m in items.items():
            if name and name.lower() in (m.get("name") or "").lower():
                slug = s
                break
        else:
            # Creala on-the-fly se abbiamo un action_text
            if not action_text:
                return (f"La scorciatoia '{name}' non esiste ancora. "
                        f"Dimmi cosa deve fare per crearla insieme al collegamento.")
            create_shortcut({"name": name, "action": action_text})
            idx = _load_index()
            items = idx.get("shortcuts", {})
            slug = _slugify(name)

    if slug not in items:
        return f"Impossibile trovare o creare la scorciatoia '{name}'."

    visible_name = items[slug].get("name") or name or slug
    desk = _desktop_dir()
    try:
        desk.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    target, arguments, working_dir = _build_exec_command_for_shortcut(slug)
    sysname = platform.system()

    if sysname == "Windows":
        lnk = desk / f"{visible_name}.lnk"
        ok  = _create_windows_lnk(
            lnk, target=target, arguments=arguments,
            working_dir=working_dir, icon=icon,
            description=f"Scorciatoia JARVIS: {visible_name}",
        )
        if not ok:
            return (f"Non sono riuscito a creare il .lnk sul desktop. "
                    f"Il file dovrebbe apparire come: {lnk}")
        # Aggiorna l'index con la posizione del collegamento fisico
        items[slug]["desktop_shortcut"] = str(lnk)
        _save_index(idx)
        return f"Ho messo la scorciatoia '{visible_name}' sul tuo desktop, capo."

    if sysname == "Darwin":
        cmd_file = desk / f"{visible_name}.command"
        exec_cmd = f'cd "{working_dir}" && "{target}" {arguments}'
        if not _create_mac_command_file(cmd_file, exec_cmd):
            return f"Non sono riuscito a creare la scorciatoia in {cmd_file}."
        items[slug]["desktop_shortcut"] = str(cmd_file)
        _save_index(idx)
        return f"Ho messo '{visible_name}.command' sul tuo desktop, capo."

    # Linux
    desktop_file = desk / f"{visible_name}.desktop"
    exec_cmd = f'{target} {arguments}'
    if not _create_linux_desktop_file(
            desktop_file, exec_cmd=exec_cmd,
            name=visible_name, icon=icon,
            comment=f"Scorciatoia JARVIS: {visible_name}"):
        return f"Non sono riuscito a creare {desktop_file}."
    items[slug]["desktop_shortcut"] = str(desktop_file)
    _save_index(idx)
    return f"Ho creato '{visible_name}.desktop' sul desktop, capo."


def remove_desktop_shortcut(parameters: Optional[dict] = None,
                            response=None, player=None,
                            session_memory=None) -> str:
    """Rimuove la scorciatoia fisica dal desktop (mantiene quella logica)."""
    params = parameters or {}
    name    = (params.get("name") or "").strip()
    slug_in = (params.get("slug") or "").strip()
    if not name and not slug_in:
        return "Capo, quale scorciatoia devo togliere dal desktop?"

    _ensure_dirs()
    idx = _load_index()
    items = idx.get("shortcuts", {})
    slug = _slugify(slug_in or name)

    if slug not in items:
        for s, m in items.items():
            if name and name.lower() in (m.get("name") or "").lower():
                slug = s
                break

    if slug not in items:
        return f"Scorciatoia '{name}' non trovata."

    path_str = items[slug].get("desktop_shortcut")
    if not path_str:
        return f"'{name}' non ha una scorciatoia fisica sul desktop."

    try:
        p = Path(path_str)
        if p.exists():
            p.unlink()
        items[slug].pop("desktop_shortcut", None)
        _save_index(idx)
        return f"Scorciatoia '{name}' rimossa dal desktop, capo."
    except Exception as e:
        return f"Errore rimuovendo la scorciatoia dal desktop: {e}"



def _ensure_dirs():
    SHORTCUTS_DIR.mkdir(parents=True, exist_ok=True)
    init = SHORTCUTS_DIR / "__init__.py"
    if not init.exists():
        init.write_text("# scorciatoie generate da Jarvis\n", encoding="utf-8")


def _load_index() -> dict:
    if not INDEX_FILE.exists():
        return {"shortcuts": {}}
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"shortcuts": {}}


def _save_index(idx: dict) -> None:
    INDEX_FILE.write_text(
        json.dumps(idx, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------
# Classificazione del comando "cosa deve fare"
# ---------------------------------------------------------------
_SEARCH_KWS = ("cerca", "ricerca", "ricerca su google", "googla", "trova ", "cerca su")
_CHATGPT_KWS = ("chatgpt", "chat gpt", "openai chat", "apri chatgpt", "vai su chatgpt")
_OPENAPP_KWS = ("apri ", "lancia ", "avvia app ", "avvia applicazione", "esegui app ")
_OPENFILE_KWS = ("avvia ", "esegui ", "apri file ", "lancia file ", "avvia file ")
_URL_RE = re.compile(r"^(https?://\S+)$", re.IGNORECASE)


def _classify_action(text: str) -> dict:
    t = (text or "").strip()
    tl = t.lower()

    if not t:
        return {"kind": "noop", "raw": text}

    # URL diretto
    if _URL_RE.match(t):
        return {"kind": "open_url", "url": t}

    # ChatGPT
    if any(k in tl for k in _CHATGPT_KWS):
        return {"kind": "open_url", "url": "https://chat.openai.com/"}

    # Ricerca su Google (Firefox)
    for kw in _SEARCH_KWS:
        if tl.startswith(kw):
            q = t[len(kw):].strip(" :,.")
            return {"kind": "search", "query": q or t}
    if "ricerca" in tl or "cerca" in tl:
        # rimuovi parola "ricerca/cerca" e usa il resto
        q = re.sub(r"^(cerca|ricerca|googla)\b[:\s]*", "", tl).strip()
        return {"kind": "search", "query": q or t}

    # Apri / lancia file (path)
    for kw in _OPENFILE_KWS:
        if kw in tl:
            target = t.split(kw, 1)[1].strip().strip('"').strip("'")
            if target and (os.path.sep in target or "/" in target or target.lower().endswith(
                    (".exe", ".bat", ".cmd", ".sh", ".lnk", ".app", ".py", ".ps1"))):
                return {"kind": "run_file", "path": target}

    # Path "raw" (anche senza keyword): es. "C:\\Users\\...\\file.bat"
    stripped = t.strip().strip('"').strip("'")
    if stripped.lower().endswith(
            (".exe", ".bat", ".cmd", ".sh", ".lnk", ".app", ".py", ".ps1")):
        return {"kind": "run_file", "path": stripped}
    if re.match(r"^[A-Za-z]:[\\/]", stripped) or stripped.startswith("/"):
        return {"kind": "run_file", "path": stripped}

    # Apri app per nome
    for kw in _OPENAPP_KWS:
        if tl.startswith(kw):
            app_name = t[len(kw):].strip()
            return {"kind": "open_app", "app_name": app_name}

    # Generico: prova run_file se sembra un path
    if os.path.sep in t and Path(t).exists():
        return {"kind": "run_file", "path": t}

    # Fallback: trattalo come query di ricerca
    return {"kind": "search", "query": t}


# ---------------------------------------------------------------
# Code generator
# ---------------------------------------------------------------
def _render_shortcut_code(name: str, slug: str, action: dict) -> str:
    kind = action.get("kind")
    header = (
        f'"""Scorciatoia auto-generata da Jarvis.\n'
        f'\n'
        f'    Nome     : {name}\n'
        f'    Slug     : {slug}\n'
        f'    Tipo     : {kind}\n'
        f'    Creata il: {datetime.now().isoformat(timespec="seconds")}\n'
        f'"""\n'
        f'import os, sys, subprocess, webbrowser, urllib.parse, platform\n\n'
    )

    if kind == "search":
        q = action.get("query", "")
        body = (
            f'def run():\n'
            f'    url = "https://www.google.com/search?q=" + urllib.parse.quote({q!r})\n'
            f'    # Apri SEMPRE su Firefox quando possibile\n'
            f'    try:\n'
            f'        webbrowser.get("firefox").open(url)\n'
            f'        return f"Cerco {q!r} su Firefox."\n'
            f'    except Exception:\n'
            f'        webbrowser.open(url)\n'
            f'        return f"Cerco {q!r} sul browser di default."\n'
        )
    elif kind == "open_url":
        u = action.get("url", "")
        body = (
            f'def run():\n'
            f'    try:\n'
            f'        webbrowser.get("firefox").open({u!r})\n'
            f'        return "Apro {u} su Firefox."\n'
            f'    except Exception:\n'
            f'        webbrowser.open({u!r})\n'
            f'        return "Apro {u} sul browser di default."\n'
        )
    elif kind == "run_file":
        # Normalizza il path: usa forward-slash (validi anche su Windows)
        # e poi codificalo con json.dumps per garantire l'assenza di
        # sequenze unicode-escape rotte (\U, \N, \x...).
        p = action.get("path", "")
        p_norm = p.replace("\\", "/")
        path_literal = json.dumps(p_norm, ensure_ascii=False)
        body = (
            f'def run():\n'
            f'    path = {path_literal}\n'
            f'    if not os.path.exists(path):\n'
            f'        return f"File non trovato: {{path}}"\n'
            f'    ext = os.path.splitext(path)[1].lower()\n'
            f'    try:\n'
            f'        if platform.system() == "Windows":\n'
            f'            if ext in (".bat", ".cmd"):\n'
            f'                # I .bat hanno bisogno di shell=True / cmd /c\n'
            f'                subprocess.Popen(["cmd", "/c", path],\n'
            f'                                 cwd=os.path.dirname(path) or None,\n'
            f'                                 creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))\n'
            f'            elif ext == ".ps1":\n'
            f'                subprocess.Popen(["powershell", "-ExecutionPolicy", "Bypass",\n'
            f'                                  "-File", path])\n'
            f'            elif ext == ".py":\n'
            f'                subprocess.Popen([sys.executable, path])\n'
            f'            else:\n'
            f'                os.startfile(path)\n'
            f'        elif platform.system() == "Darwin":\n'
            f'            subprocess.Popen(["open", path])\n'
            f'        else:\n'
            f'            subprocess.Popen(["xdg-open", path])\n'
            f'        return f"Eseguo {{path}}."\n'
            f'    except Exception as e:\n'
            f'        return f"Errore avviando {{path}}: {{e}}"\n'
        )
    elif kind == "open_app":
        a = action.get("app_name", "")
        body = (
            f'def run():\n'
            f'    app = {a!r}\n'
            f'    # Tentativo 1: chiama il modulo open_app del progetto\n'
            f'    try:\n'
            f'        from actions.open_app import open_app\n'
            f'        return open_app(parameters={{"app_name": app}})\n'
            f'    except Exception as e:\n'
            f'        # Tentativo 2: avvio diretto\n'
            f'        try:\n'
            f'            if platform.system() == "Windows":\n'
            f'                subprocess.Popen(["start", "", app], shell=True)\n'
            f'            else:\n'
            f'                subprocess.Popen([app])\n'
            f'            return f"Apro {{app}}."\n'
            f'        except Exception as e2:\n'
            f'            return f"Impossibile aprire {{app}}: {{e2}}"\n'
        )
    else:
        body = (
            'def run():\n'
            '    return "Scorciatoia vuota: nessuna azione configurata."\n'
        )

    main_block = (
        '\n\nif __name__ == "__main__":\n'
        '    print(run())\n'
    )
    return header + body + main_block


# ---------------------------------------------------------------
# Public API
# ---------------------------------------------------------------
def create_shortcut(parameters: Optional[dict] = None,
                    response=None, player=None, session_memory=None) -> str:
    """Crea (o sovrascrive) una scorciatoia.

    parameters:
        name:    nome scorciatoia (es. "ricerca tonno")
        action:  cosa deve fare in linguaggio naturale
                 (es. "cerca tonno fresco", "apri chatgpt",
                  "avvia C:/Games/X.exe")
    """
    params = parameters or {}
    name   = (params.get("name")   or "").strip()
    action_text = (params.get("action") or params.get("do") or "").strip()

    if not name:
        return "Capo, dimmi il nome della scorciatoia."
    if not action_text:
        return f"Capo, cosa deve fare la scorciatoia '{name}'?"

    _ensure_dirs()
    slug = _slugify(name)
    if not slug:
        return "Nome scorciatoia non valido."

    action = _classify_action(action_text)
    code = _render_shortcut_code(name, slug, action)

    target = SHORTCUTS_DIR / f"{slug}.py"
    target.write_text(code, encoding="utf-8")

    # Update index
    idx = _load_index()
    idx.setdefault("shortcuts", {})[slug] = {
        "name":   name,
        "file":   f"scorciatoie/{slug}.py",
        "action": action,
        "raw":    action_text,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save_index(idx)

    if player:
        try:
            player.write_log(f"SYS: shortcut created -> {name} ({slug})")
        except Exception:
            pass

    return (f"Scorciatoia '{name}' creata in scorciatoie/{slug}.py "
            f"(tipo: {action.get('kind')}).")


def list_shortcuts(parameters=None, **_) -> str:
    _ensure_dirs()
    idx = _load_index()
    items = idx.get("shortcuts", {})
    if not items:
        return "Nessuna scorciatoia ancora creata, capo."
    lines = ["Scorciatoie disponibili:"]
    for slug, meta in items.items():
        lines.append(f" - {meta.get('name', slug)} [{slug}] -> {meta.get('action', {}).get('kind')}")
    return "\n".join(lines)


def run_shortcut(parameters: Optional[dict] = None,
                 response=None, player=None, session_memory=None) -> str:
    """Esegue una scorciatoia esistente per nome o slug."""
    params = parameters or {}
    name = (params.get("name") or params.get("slug") or "").strip()
    if not name:
        return "Capo, quale scorciatoia devo eseguire?"

    _ensure_dirs()
    idx = _load_index()
    items = idx.get("shortcuts", {})

    # match per slug esatto
    slug = _slugify(name)
    meta = items.get(slug)

    # fallback: match parziale per name
    if meta is None:
        for s, m in items.items():
            if name.lower() in (m.get("name") or "").lower():
                slug, meta = s, m
                break

    if meta is None:
        return f"Scorciatoia '{name}' non trovata."

    path = SHORTCUTS_DIR / f"{slug}.py"
    if not path.exists():
        return f"Il file della scorciatoia '{name}' non esiste piu'."

    # import dinamico e chiama run()
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"scorciatoie.{slug}", path)
    mod  = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)  # type: ignore
        if hasattr(mod, "run"):
            return str(mod.run() or f"Eseguita scorciatoia '{meta.get('name')}'.")
        return "La scorciatoia non espone la funzione run()."
    except Exception as e:
        return f"Errore eseguendo la scorciatoia: {e}"


if __name__ == "__main__":
    # quick self-test
    print(create_shortcut({"name": "ricerca tonno", "action": "cerca tonno fresco"}))
    print(list_shortcuts())
    print(run_shortcut({"name": "ricerca tonno"}))

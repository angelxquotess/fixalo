import os
import shutil
import platform
import subprocess
from pathlib import Path
from datetime import datetime
from functools import lru_cache

try:
    import send2trash
    _SEND2TRASH = True
except ImportError:
    _SEND2TRASH = False


# ============================================================
# SYSTEM
# ============================================================

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"


# ============================================================
# SAFETY
# ============================================================

_SAFE_ROOTS: list[Path] = [
    Path.home(),
]


@lru_cache(maxsize=16)
def _resolved_safe_roots() -> tuple[Path, ...]:
    """
    Cache delle root sicure.
    Evita di chiamare resolve() ripetutamente durante le operazioni.
    """
    roots = []

    for root in _SAFE_ROOTS:
        try:
            roots.append(root.resolve())
        except Exception:
            continue

    return tuple(roots)


def _is_safe_path(target: Path) -> bool:
    """Verifica che il path sia contenuto nelle directory consentite."""
    try:
        resolved = target.resolve()

        for root in _resolved_safe_roots():
            if resolved == root or resolved.is_relative_to(root):
                return True

        return False

    except Exception:
        return False


# ============================================================
# SPECIAL DIRECTORIES
# ============================================================

def _get_desktop() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DESKTOP_DIR", "").strip()

        if xdg:
            path = Path(xdg).expanduser()
            if path.exists():
                return path

    return Path.home() / "Desktop"


def _get_downloads() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DOWNLOAD_DIR", "").strip()

        if xdg:
            path = Path(xdg).expanduser()
            if path.exists():
                return path

    return Path.home() / "Downloads"


def _get_documents() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DOCUMENTS_DIR", "").strip()

        if xdg:
            path = Path(xdg).expanduser()
            if path.exists():
                return path

    return Path.home() / "Documents"


def _get_pictures() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_PICTURES_DIR", "").strip()

        if xdg:
            path = Path(xdg).expanduser()
            if path.exists():
                return path

    return Path.home() / "Pictures"


def _get_music() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_MUSIC_DIR", "").strip()

        if xdg:
            path = Path(xdg).expanduser()
            if path.exists():
                return path

    return Path.home() / "Music"


def _get_videos() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_VIDEOS_DIR", "").strip()

        if xdg:
            path = Path(xdg).expanduser()
            if path.exists():
                return path

    return Path.home() / "Videos"


# ============================================================
# PATH RESOLUTION
# ============================================================

def _resolve_shortcut(name: str) -> Path | None:
    """
    Risolve una shortcut solo quando viene effettivamente richiesta.

    Prima versione:
        costruiva tutte le Path ad ogni chiamata.

    Versione ottimizzata:
        calcola solamente quella necessaria.
    """
    name = name.lower()

    if name == "desktop":
        return _get_desktop()

    if name == "downloads":
        return _get_downloads()

    if name == "documents":
        return _get_documents()

    if name == "pictures":
        return _get_pictures()

    if name == "music":
        return _get_music()

    if name == "videos":
        return _get_videos()

    if name == "home":
        return Path.home()

    return None


def _resolve_path(raw: str) -> Path:
    """
    Risolve shortcut e path normali.

    Supporta:
        desktop
        downloads
        documents
        pictures
        music
        videos
        home

    e:
        desktop/file.txt
        downloads/file.pdf
        documents/test.docx
    """

    raw = (raw or "").strip()

    if not raw:
        return _get_desktop()

    # Shortcut completa.
    shortcut = _resolve_shortcut(raw)

    if shortcut is not None:
        return shortcut

    # Normalizza slash Windows/Linux.
    normalized = raw.replace("\\", "/")

    parts = normalized.split("/", 1)

    if len(parts) == 2:
        prefix, remainder = parts
        base = _resolve_shortcut(prefix)

        if base is not None:
            return base / remainder

    # Path normale.
    return Path(raw).expanduser()


# ============================================================
# FILE SEARCH
# ============================================================

def _find_by_name(name, roots=None, max_depth=4):
    """
    Ricerca ricorsiva per nome file/cartella.

    La ricerca esatta viene effettuata prima.
    La ricerca parziale viene utilizzata solo come fallback.
    """

    if not name:
        return None

    if roots is None:
        roots = [
            _get_desktop(),
            _get_downloads(),
            _get_documents(),
            _get_pictures(),
            _get_music(),
            _get_videos(),
            Path.home(),
        ]

    target_lower = name.lower()

    seen = set()

    # --------------------------------------------------------
    # EXACT / CONTROLLED SEARCH
    # --------------------------------------------------------

    for root in roots:

        try:
            if not root.exists():
                continue
        except Exception:
            continue

        queue = [(root, 0)]

        while queue:
            cur, depth = queue.pop(0)

            try:
                resolved_cur = cur.resolve()
            except Exception:
                resolved_cur = cur

            if resolved_cur in seen:
                continue

            seen.add(resolved_cur)

            try:
                for item in cur.iterdir():

                    try:
                        if item.name.lower() == target_lower:
                            return item
                    except Exception:
                        continue

                    if (
                        item.is_dir()
                        and depth < max_depth
                        and not item.name.startswith(".")
                    ):
                        queue.append((item, depth + 1))

            except (PermissionError, OSError):
                continue

    # --------------------------------------------------------
    # PARTIAL FALLBACK
    # --------------------------------------------------------

    for root in roots:

        try:
            if not root.exists():
                continue

            for item in root.rglob("*"):

                try:
                    if target_lower in item.name.lower():
                        return item
                except Exception:
                    continue

        except (PermissionError, OSError):
            continue

    return None


def _resolve_target(path, name=""):
    """
    Risolve una destinazione.

    FAST PATH:
        se il path esiste, ritorna immediatamente.

    FALLBACK:
        ricerca ricorsiva solo se necessario.
    """

    base = _resolve_path(path)

    target = (base / name) if name else base

    # ========================================================
    # FAST PATH
    # ========================================================

    if target.exists():
        return target

    # ========================================================
    # FALLBACK SEARCH
    # ========================================================

    search_name = name or target.name

    if search_name and search_name != base.name:

        found = _find_by_name(search_name)

        if found is not None:
            return found

    return target


# ============================================================
# SIZE
# ============================================================

def _format_size(b: int) -> str:
    size = float(b)

    for unit in ["B", "KB", "MB", "GB", "TB"]:

        if size < 1024:
            return f"{size:.1f} {unit}"

        size /= 1024

    return f"{size:.1f} TB"


# ============================================================
# TRASH
# ============================================================

def _safe_trash(target: Path) -> str:

    if not _SEND2TRASH:
        return (
            "send2trash is not installed. "
            "Run: pip install send2trash — "
            "Permanent deletion is disabled for safety."
        )

    send2trash.send2trash(str(target))

    return f"Moved to Trash: {target.name}"


# ============================================================
# OPEN / LAUNCH
# ============================================================

def _launch_target(target: Path) -> str:
    """
    Avvia direttamente il target nel modo più veloce possibile.

    Windows:
        os.startfile()

    macOS:
        open

    Linux:
        eseguibile -> avvio diretto
        file/cartella -> xdg-open

    Nessun processo viene atteso.
    """

    target_str = str(target)

    try:

        # ====================================================
        # WINDOWS
        # ====================================================

        if _OS == "Windows":

            os.startfile(target_str)  # type: ignore[attr-defined]

            return f"Opened: {target.name}"

        # ====================================================
        # MACOS
        # ====================================================

        if _OS == "Darwin":

            subprocess.Popen(
                ["open", target_str],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            return f"Opened: {target.name}"

        # ====================================================
        # LINUX / UNIX
        # ====================================================

        # Se è direttamente eseguibile, NON usare xdg-open.
        if target.is_file() and os.access(target_str, os.X_OK):

            subprocess.Popen(
                [target_str],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

            return f"Opened: {target.name}"

        # ----------------------------------------------------
        # File/cartelle normali
        # ----------------------------------------------------

        subprocess.Popen(
            ["xdg-open", target_str],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        return f"Opened: {target.name}"

    except FileNotFoundError:

        return (
            f"Could not open '{target.name}': "
            "required system launcher was not found."
        )

    except PermissionError:

        return f"Permission denied: {target.name}"

    except Exception as e:

        return f"Could not open file: {e}"


def open_file(path: str, name: str = "") -> str:
    """
    Apertura ottimizzata.

    IMPORTANTE:
    Non utilizza _resolve_target() direttamente perché per l'apertura
    vogliamo mantenere il percorso più veloce possibile.

    1. Risoluzione diretta.
    2. exists() immediato.
    3. Solo in caso di fallimento ricerca ricorsiva.
    """

    try:

        # ====================================================
        # FAST PATH
        # ====================================================

        base = _resolve_path(path)

        target = (base / name) if name else base

        if target.exists():

            if not _is_safe_path(target):
                return f"Access denied: {target}"

            return _launch_target(target)

        # ====================================================
        # FALLBACK SEARCH
        # ====================================================

        search_name = name or target.name

        if search_name:

            found = _find_by_name(search_name)

            if found is not None:

                if not _is_safe_path(found):
                    return f"Access denied: {found}"

                return _launch_target(found)

        return f"File not found: {name or path}"

    except PermissionError:

        return f"Permission denied: {path}"

    except Exception as e:

        return f"Could not open file: {e}"


# ============================================================
# LIST
# ============================================================

def list_files(path: str = "desktop", show_hidden: bool = False) -> str:

    try:

        target = _resolve_target(path)

        if not _is_safe_path(target):
            return f"Access denied: {target}"

        if not target.exists():
            return f"Path not found: {target}"

        if not target.is_dir():
            return f"Not a directory: {target}"

        items = []

        for item in sorted(target.iterdir()):

            if not show_hidden and item.name.startswith("."):
                continue

            if item.is_dir():

                items.append(f"📁 {item.name}/")

            else:

                try:
                    size = _format_size(item.stat().st_size)
                except Exception:
                    size = "?"

                items.append(
                    f"📄 {item.name} ({size})"
                )

        if not items:
            return f"Directory is empty: {target.name}/"

        return (
            f"Contents of {target.name}/ "
            f"({len(items)} items):\n"
            + "\n".join(items)
        )

    except PermissionError:

        return f"Permission denied: {path}"

    except Exception as e:

        return f"Error listing files: {e}"


# ============================================================
# CREATE FILE
# ============================================================

def create_file(
    path: str,
    name: str = "",
    content: str = "",
) -> str:

    try:

        base = _resolve_path(path)

        target = (base / name) if name else base

        if not _is_safe_path(target):
            return f"Access denied: {target}"

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        target.write_text(
            content,
            encoding="utf-8",
        )

        return f"File created: {target.name}"

    except Exception as e:

        return f"Could not create file: {e}"


# ============================================================
# CREATE FOLDER
# ============================================================

def create_folder(
    path: str,
    name: str = "",
) -> str:

    try:

        base = _resolve_path(path)

        target = (base / name) if name else base

        if not _is_safe_path(target):
            return f"Access denied: {target}"

        target.mkdir(
            parents=True,
            exist_ok=True,
        )

        return f"Folder created: {target.name}"

    except Exception as e:

        return f"Could not create folder: {e}"


# ============================================================
# DELETE
# ============================================================

def delete_file(
    path: str,
    name: str = "",
) -> str:

    try:

        base = _resolve_path(path)

        target = (base / name) if name else base

        if not _is_safe_path(target):
            return f"Access denied: {target}"

        if not target.exists():
            return f"Not found: {target.name}"

        # ----------------------------------------------------
        # Protected directories
        # ----------------------------------------------------

        protected = {
            _get_desktop(),
            _get_downloads(),
            _get_documents(),
            _get_pictures(),
            _get_music(),
            _get_videos(),
            Path.home(),
        }

        protected_resolved = {
            p.resolve()
            for p in protected
        }

        if target.resolve() in protected_resolved:

            return (
                f"Protected directory, "
                f"cannot delete: {target.name}"
            )

        return _safe_trash(target)

    except PermissionError:

        return f"Permission denied: {path}"

    except Exception as e:

        return f"Could not delete: {e}"


# ============================================================
# MOVE
# ============================================================

def move_file(
    path: str,
    name: str = "",
    destination: str = "",
) -> str:

    try:

        base = _resolve_path(path)

        src = (base / name) if name else base

        dst = (
            _resolve_path(destination)
            if destination
            else None
        )

        if not src.exists():
            return f"Source not found: {src.name}"

        if dst is None:
            return "No destination specified."

        if not _is_safe_path(src):
            return f"Access denied (source): {src}"

        if not _is_safe_path(dst):
            return f"Access denied (destination): {dst}"

        if dst.is_dir():
            dst = dst / src.name

        dst.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.move(
            str(src),
            str(dst),
        )

        return (
            f"Moved: {src.name} "
            f"→ {dst.parent.name}/"
        )

    except Exception as e:

        return f"Could not move: {e}"


# ============================================================
# COPY
# ============================================================

def copy_file(
    path: str,
    name: str = "",
    destination: str = "",
) -> str:

    try:

        base = _resolve_path(path)

        src = (base / name) if name else base

        dst = (
            _resolve_path(destination)
            if destination
            else None
        )

        if not src.exists():
            return f"Source not found: {src.name}"

        if dst is None:
            return "No destination specified."

        if not _is_safe_path(src):
            return f"Access denied (source): {src}"

        if not _is_safe_path(dst):
            return f"Access denied (destination): {dst}"

        if dst.is_dir():
            dst = dst / src.name

        dst.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if src.is_dir():

            shutil.copytree(
                str(src),
                str(dst),
            )

        else:

            shutil.copy2(
                str(src),
                str(dst),
            )

        return (
            f"Copied: {src.name} "
            f"→ {dst.parent.name}/"
        )

    except Exception as e:

        return f"Could not copy: {e}"


# ============================================================
# RENAME
# ============================================================

def rename_file(
    path: str,
    name: str = "",
    new_name: str = "",
) -> str:

    try:

        base = _resolve_path(path)

        target = (base / name) if name else base

        if not _is_safe_path(target):
            return f"Access denied: {target}"

        if not target.exists():
            return f"Not found: {target.name}"

        if not new_name:
            return "No new name provided."

        new_path = target.parent / new_name

        if new_path.exists():
            return (
                f"A file named "
                f"'{new_name}' already exists here."
            )

        old_name = target.name

        target.rename(new_path)

        return (
            f"Renamed: {old_name} "
            f"→ {new_name}"
        )

    except Exception as e:

        return f"Could not rename: {e}"


# ============================================================
# READ
# ============================================================

def read_file(
    path: str,
    name: str = "",
    max_chars: int = 4000,
) -> str:

    try:

        target = _resolve_target(
            path,
            name,
        )

        if not _is_safe_path(target):
            return f"Access denied: {target}"

        if not target.exists():
            return f"File not found: {target.name}"

        if not target.is_file():
            return f"Not a file: {target.name}"

        content = target.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        if len(content) > max_chars:

            content = (
                content[:max_chars]
                + f"\n\n[Truncated — "
                f"{len(content)} total chars]"
            )

        return content

    except Exception as e:

        return f"Could not read file: {e}"


# ============================================================
# WRITE
# ============================================================

def write_file(
    path: str,
    name: str = "",
    content: str = "",
    append: bool = False,
) -> str:

    try:

        base = _resolve_path(path)

        target = (base / name) if name else base

        if not _is_safe_path(target):
            return f"Access denied: {target}"

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        mode = "a" if append else "w"

        with open(
            target,
            mode,
            encoding="utf-8",
        ) as f:

            f.write(content)

        action = (
            "Appended to"
            if append
            else "Written to"
        )

        return f"{action}: {target.name}"

    except Exception as e:

        return f"Could not write file: {e}"


# ============================================================
# FIND FILES
# ============================================================

def find_files(
    name: str = "",
    extension: str = "",
    path: str = "home",
    max_results: int = 20,
) -> str:

    try:

        search_path = _resolve_path(path)

        if not _is_safe_path(search_path):
            return f"Access denied: {search_path}"

        if not search_path.exists():
            return f"Search path not found: {path}"

        max_results = max(
            1,
            min(int(max_results), 50),
        )

        results = []

        dir_count = 0

        max_dirs = 500

        for item in search_path.rglob("*"):

            if item.is_dir():

                dir_count += 1

                if dir_count > max_dirs:
                    break

                continue

            if not item.is_file():
                continue

            if (
                extension
                and item.suffix.lower()
                != extension.lower()
            ):
                continue

            if (
                name
                and name.lower()
                not in item.name.lower()
            ):
                continue

            try:
                size = _format_size(
                    item.stat().st_size
                )
            except Exception:
                size = "?"

            results.append(
                f"📄 {item.name} "
                f"({size}) — {item.parent}"
            )

            if len(results) >= max_results:
                break

        if not results:

            query = (
                name
                or extension
                or "files"
            )

            return (
                f"No {query} found "
                f"in {search_path.name}/"
            )

        return (
            f"Found {len(results)} file(s):\n"
            + "\n".join(results)
        )

    except Exception as e:

        return f"Search error: {e}"


# ============================================================
# LARGEST FILES
# ============================================================

def get_largest_files(
    path: str = "downloads",
    count: int = 10,
) -> str:

    count = max(
        1,
        min(int(count), 50),
    )

    try:

        search_path = _resolve_path(path)

        if not _is_safe_path(search_path):
            return f"Access denied: {search_path}"

        if not search_path.exists():
            return f"Path not found: {path}"

        files = []

        for item in search_path.rglob("*"):

            if item.is_file():

                try:

                    files.append(
                        (
                            item.stat().st_size,
                            item,
                        )
                    )

                except Exception:
                    continue

        files.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        top = files[:count]

        if not top:
            return "No files found."

        lines = [
            f"Top {len(top)} largest files "
            f"in {search_path.name}/:"
        ]

        for size, file_path in top:

            lines.append(
                f"  {_format_size(size):>10}  "
                f"{file_path.name}  "
                f"({file_path.parent})"
            )

        return "\n".join(lines)

    except Exception as e:

        return f"Error: {e}"


# ============================================================
# DISK USAGE
# ============================================================

def get_disk_usage(
    path: str = "home",
) -> str:

    try:

        target = _resolve_path(path)

        if not _is_safe_path(target):
            return f"Access denied: {target}"

        usage = shutil.disk_usage(target)

        pct = (
            usage.used
            / usage.total
            * 100
            if usage.total
            else 0
        )

        return (
            f"Disk usage ({target}):\n"
            f"  Total : {_format_size(usage.total)}\n"
            f"  Used  : {_format_size(usage.used)} "
            f"({pct:.1f}%)\n"
            f"  Free  : {_format_size(usage.free)}"
        )

    except Exception as e:

        return f"Could not get disk usage: {e}"


# ============================================================
# ORGANIZE DESKTOP
# ============================================================

def organize_desktop() -> str:

    type_map = {

        "Images": {
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".bmp",
            ".webp",
            ".svg",
            ".ico",
            ".heic",
        },

        "Documents": {
            ".pdf",
            ".doc",
            ".docx",
            ".txt",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".csv",
            ".odt",
            ".ods",
            ".odp",
        },

        "Videos": {
            ".mp4",
            ".avi",
            ".mkv",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
        },

        "Music": {
            ".mp3",
            ".wav",
            ".flac",
            ".aac",
            ".ogg",
            ".wma",
            ".m4a",
        },

        "Archives": {
            ".zip",
            ".rar",
            ".7z",
            ".tar",
            ".gz",
            ".bz2",
            ".xz",
        },

        "Code": {
            ".py",
            ".js",
            ".ts",
            ".html",
            ".css",
            ".json",
            ".xml",
            ".cpp",
            ".java",
            ".cs",
            ".go",
            ".rs",
            ".sh",
        },
    }

    desktop = _get_desktop()

    moved = []
    skipped = []

    try:

        if not _is_safe_path(desktop):
            return f"Access denied: {desktop}"

        if not desktop.exists():
            return f"Desktop not found: {desktop}"

        organized_folders = set(type_map)

        organized_folders.add("Others")

        for item in desktop.iterdir():

            # ------------------------------------------------
            # Ignore folders / hidden files
            # ------------------------------------------------

            if item.is_dir():
                continue

            if item.name.startswith("."):
                continue

            if item.name in organized_folders:
                continue

            ext = item.suffix.lower()

            target_dir = desktop / "Others"

            for folder, extensions in type_map.items():

                if ext in extensions:
                    target_dir = desktop / folder
                    break

            target_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            new_path = target_dir / item.name

            if new_path.exists():

                skipped.append(item.name)

                continue

            shutil.move(
                str(item),
                str(new_path),
            )

            moved.append(
                f"{item.name} → "
                f"{target_dir.name}/"
            )

        result = (
            f"Desktop organized: "
            f"{len(moved)} files moved."
        )

        if moved:

            preview = moved[:8]

            result += (
                "\n"
                + "\n".join(preview)
            )

            if len(moved) > 8:

                result += (
                    f"\n... and "
                    f"{len(moved) - 8} more."
                )

        if skipped:

            result += (
                f"\n{len(skipped)} file(s) "
                f"skipped (name conflict)."
            )

        return result

    except Exception as e:

        return (
            f"Could not organize desktop: {e}"
        )


# ============================================================
# FILE INFO
# ============================================================

def get_file_info(
    path: str,
    name: str = "",
) -> str:

    try:

        target = _resolve_target(
            path,
            name,
        )

        if not _is_safe_path(target):
            return f"Access denied: {target}"

        if not target.exists():
            return f"Not found: {target.name}"

        stat = target.stat()

        info = {

            "Name":
                target.name,

            "Type":
                "Folder"
                if target.is_dir()
                else "File",

            "Size":
                _format_size(
                    stat.st_size
                ),

            "Location":
                str(target.parent),

            "Created":
                datetime.fromtimestamp(
                    stat.st_ctime
                ).strftime(
                    "%Y-%m-%d %H:%M"
                ),

            "Modified":
                datetime.fromtimestamp(
                    stat.st_mtime
                ).strftime(
                    "%Y-%m-%d %H:%M"
                ),

            "Extension":
                target.suffix or "—",
        }

        return "\n".join(
            f"  {key}: {value}"
            for key, value in info.items()
        )

    except Exception as e:

        return (
            f"Could not get file info: {e}"
        )


# ============================================================
# CONTROLLER
# ============================================================

def file_controller(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:

    params = parameters or {}

    action = str(
        params.get(
            "action",
            "",
        )
    ).lower().strip()

    path = params.get(
        "path",
        "desktop",
    )

    name = params.get(
        "name",
        "",
    )

    # --------------------------------------------------------
    # LOGGING
    # --------------------------------------------------------

    if player:

        try:

            player.write_log(
                f"[file] "
                f"{action} "
                f"{name or path}"
            )

        except Exception:
            pass

    # --------------------------------------------------------
    # ACTIONS
    # --------------------------------------------------------

    try:

        if action == "list":

            return list_files(path)

        elif action == "create_file":

            return create_file(
                path,
                name=name,
                content=params.get(
                    "content",
                    "",
                ),
            )

        elif action == "create_folder":

            return create_folder(
                path,
                name=name,
            )

        elif action == "delete":

            return delete_file(
                path,
                name=name,
            )

        elif action == "move":

            return move_file(
                path,
                name=name,
                destination=params.get(
                    "destination",
                    "",
                ),
            )

        elif action == "copy":

            return copy_file(
                path,
                name=name,
                destination=params.get(
                    "destination",
                    "",
                ),
            )

        elif action == "rename":

            return rename_file(
                path,
                name=name,
                new_name=params.get(
                    "new_name",
                    "",
                ),
            )

        elif action == "read":

            return read_file(
                path,
                name=name,
            )

        elif action in (
            "open",
            "launch",
            "start",
        ):

            return open_file(
                path,
                name=name,
            )

        elif action == "write":

            return write_file(
                path,
                name=name,
                content=params.get(
                    "content",
                    "",
                ),
                append=params.get(
                    "append",
                    False,
                ),
            )

        elif action == "find":

            try:

                max_results = min(
                    int(
                        params.get(
                            "max_results",
                            20,
                        )
                    ),
                    50,
                )

            except (TypeError, ValueError):

                max_results = 20

            return find_files(
                name=name or params.get(
                    "name",
                    "",
                ),
                extension=params.get(
                    "extension",
                    "",
                ),
                path=path,
                max_results=max_results,
            )

        elif action == "largest":

            try:

                count = int(
                    params.get(
                        "count",
                        10,
                    )
                )

            except (TypeError, ValueError):

                count = 10

            return get_largest_files(
                path=path,
                count=count,
            )

        elif action == "disk_usage":

            return get_disk_usage(
                path,
            )

        elif action == "organize_desktop":

            return organize_desktop()

        elif action == "info":

            return get_file_info(
                path,
                name=name,
            )

        else:

            return (
                f"Unknown action: '{action}'"
            )

    except Exception as e:

        return (
            f"File controller error "
            f"({action}): {e}"
        )
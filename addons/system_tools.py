"""addons/system_tools.py — sistema: processi, disco, pulizia, backup, power."""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from .core import human_size, run_silent

# ------------------------------------------------------------- info sistema
def system_report() -> dict:
    import platform
    import psutil
    vm = psutil.virtual_memory()
    du = shutil.disk_usage(str(Path.home()))
    return {
        "os": f"{platform.system()} {platform.release()}",
        "cpu": platform.processor() or "?",
        "cpu_cores": psutil.cpu_count(),
        "cpu_percent": psutil.cpu_percent(interval=0.3),
        "ram_total": human_size(vm.total),
        "ram_used_percent": vm.percent,
        "disk_free": human_size(du.free),
        "boot_time": time.strftime("%Y-%m-%d %H:%M", time.localtime(psutil.boot_time())),
    }

# ---------------------------------------------------------------- processi
def top_processes(n: int = 10) -> list[dict]:
    import psutil
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            procs.append(p.info)
        except Exception:
            pass
    procs.sort(key=lambda x: x.get("memory_percent") or 0, reverse=True)
    return procs[:n]

def kill_process(name: str) -> str:
    import psutil
    killed = 0
    for p in psutil.process_iter(["name"]):
        try:
            if p.info["name"] and name.lower() in p.info["name"].lower():
                p.terminate()
                killed += 1
        except Exception:
            pass
    return f"Terminati {killed} processi '{name}'."

# ---------------------------------------------------------------- disco
def biggest_items(path: str, n: int = 10) -> list[dict]:
    items = []
    base = Path(path)
    for p in base.rglob("*"):
        try:
            if p.is_file():
                items.append({"path": str(p), "size": p.stat().st_size})
        except Exception:
            pass
    items.sort(key=lambda x: x["size"], reverse=True)
    for it in items[:n]:
        it["size_human"] = human_size(it["size"])
    return items[:n]

def find_duplicates(path: str) -> list[list[str]]:
    hashes: dict[str, list[str]] = {}
    for p in Path(path).rglob("*"):
        try:
            if p.is_file() and p.stat().st_size > 1024:
                h = hashlib.md5(p.read_bytes()).hexdigest()
                hashes.setdefault(h, []).append(str(p))
        except Exception:
            pass
    return [v for v in hashes.values() if len(v) > 1]

def organize_folder(path: str) -> str:
    """Sposta i file in sottocartelle per estensione."""
    base = Path(path)
    moved = 0
    for p in list(base.iterdir()):
        if p.is_file():
            ext = p.suffix.lower().lstrip(".") or "senza_estensione"
            dest_dir = base / ext
            dest_dir.mkdir(exist_ok=True)
            try:
                shutil.move(str(p), str(dest_dir / p.name))
                moved += 1
            except Exception:
                pass
    return f"Organizzati {moved} file in sottocartelle per estensione."

# ---------------------------------------------------------------- pulizia
def clean_temp(older_than_days: int = 1) -> str:
    tmp = Path(tempfile.gettempdir())
    cutoff = time.time() - older_than_days * 86400
    removed, freed = 0, 0
    for p in tmp.rglob("*"):
        try:
            if p.is_file() and p.stat().st_mtime < cutoff:
                freed += p.stat().st_size
                p.unlink()
                removed += 1
        except Exception:
            pass
    return f"Rimossi {removed} file temporanei, liberati {human_size(freed)}."

# ---------------------------------------------------------------- backup
def backup_folder(src: str, dest_dir: str) -> str:
    src_p = Path(src)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = Path(dest_dir) / f"backup_{src_p.name}_{stamp}.zip"
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in src_p.rglob("*"):
            if p.is_file():
                try:
                    z.write(p, p.relative_to(src_p))
                except Exception:
                    pass
    return f"Backup creato: {dest} ({human_size(dest.stat().st_size)})"

# ---------------------------------------------------------------- power
def power(action: str, delay_min: int = 0) -> str:
    """action: shutdown | restart | sleep | lock"""
    delay_s = int(delay_min) * 60
    if sys.platform.startswith("win"):
        cmds = {
            "shutdown": ["shutdown", "/s", "/t", str(delay_s)],
            "restart":  ["shutdown", "/r", "/t", str(delay_s)],
            "sleep":    ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
            "lock":     ["rundll32.exe", "user32.dll,LockWorkStation"],
        }
    else:
        cmds = {
            "shutdown": ["systemctl", "poweroff"],
            "restart":  ["systemctl", "reboot"],
            "sleep":    ["systemctl", "suspend"],
            "lock":     ["loginctl", "lock-session"],
        }
    cmd = cmds.get(action)
    if not cmd:
        return f"Azione '{action}' non valida."
    rc, out = run_silent(cmd)
    return "OK" if rc == 0 else f"Errore: {out[:200]}"

# ------------------------------------------------------------- ricerca file
def find_files(pattern: str, root: str, limit: int = 20) -> list[str]:
    out = []
    for p in Path(root).rglob(pattern):
        out.append(str(p))
        if len(out) >= limit:
            break
    return out

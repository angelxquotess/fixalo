"""addons/core.py — helper condivisi per tutti gli addon JARVIS."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "addons" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def store_path(name: str) -> Path:
    return DATA_DIR / f"{name}.json"


def load_store(name: str, default):
    p = store_path(name)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_store(name: str, data) -> None:
    store_path(name).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def run_silent(cmd: list[str], timeout: int = 10) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return 1, str(e)


def notify(title: str, message: str) -> None:
    """Notifica di sistema best-effort (Windows toast / notify-send)."""
    try:
        if sys.platform.startswith("win"):
            from win10toast import ToastNotifier
            ToastNotifier().show_toast(title, message, duration=4, threaded=True)
        else:
            run_silent(["notify-send", title, message], timeout=3)
    except Exception:
        pass


def run_later(seconds: float, fn, *args, **kwargs) -> threading.Timer:
    t = threading.Timer(seconds, fn, args=args, kwargs=kwargs)
    t.daemon = True
    t.start()
    return t


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"

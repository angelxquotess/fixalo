"""
start_jarvis_cmd.py
===================
Avvio CMD-only di JARVIS su Windows: stesse funzioni di start_jarvis.py
ma SENZA la GUI PyQt6. Si interagisce dal prompt dei comandi.

Sostituisce start_quasi.bat. Doppio click oppure:
    python start_jarvis_cmd.py

La logica e' identica a start_jarvis.py: stessa pipeline JarvisLive,
stessi tool, stesse notifiche multi-piattaforma. Cambia solo l'UI:
una ConsoleUI prende il posto di JarvisUI (vedi main_headless.py).
"""
from __future__ import annotations
import os
import sys
import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEPS_FLAG = BASE_DIR / ".deps_ok"
REQUIREMENTS = BASE_DIR / "requirements.txt"


def _ensure_deps() -> None:
    if DEPS_FLAG.is_file() or not REQUIREMENTS.is_file():
        return
    print("[JARVIS] Installazione dipendenze (solo la prima volta)...")
    cmd = [sys.executable, "-m", "pip", "install",
           "--disable-pip-version-check", "-r", str(REQUIREMENTS)]
    rc = subprocess.call(cmd)
    if rc == 0:
        DEPS_FLAG.write_text("ok", encoding="utf-8")
    else:
        print("[JARVIS] Alcune dipendenze non sono state installate (proseguo).")


def _lower_cpu_priority() -> None:
    try:
        import psutil
        p = psutil.Process()
        if sys.platform.startswith("win"):
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        else:
            p.nice(5)
    except Exception:
        pass


def main() -> None:
    os.chdir(str(BASE_DIR))
    _ensure_deps()
    _lower_cpu_priority()

    print("=" * 60)
    print("  JARVIS — Avvio CMD ONLY (no GUI, stessa logica)")
    print("=" * 60)

    from main_headless import main as headless_main
    headless_main()


if __name__ == "__main__":
    main()

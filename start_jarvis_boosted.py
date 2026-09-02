"""
start_jarvis_boosted.py — Avvio JARVIS ottimizzato (ADDITIVO).

Identico a start_jarvis.py, ma applica prima `jarvis_perf` (cache, FPS
adattivi, GC tuning, flag Qt). Il launcher originale resta intatto.

    python start_jarvis_boosted.py
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


def main() -> None:
    os.chdir(str(BASE_DIR))
    _ensure_deps()

    import jarvis_perf
    jarvis_perf.apply()

    print("=" * 60)
    print("  JARVIS — Avvio BOOSTED (performance patch attiva)")
    print("=" * 60)

    from main import main as jarvis_main
    jarvis_main()


if __name__ == "__main__":
    main()

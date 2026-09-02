"""
start_jarvis.py
===============
Avvio COMPLETO di JARVIS su Windows: GUI PyQt6 + voce + tool calling +
dashboard messaggi + notifiche multi-piattaforma.

Sostituisce start_quasi_gui.bat. Doppio click oppure:
    python start_jarvis.py

Caratteristiche:
- Installa le dipendenze al primo avvio (.deps_ok flag).
- Imposta priorita' BelowNormal del processo Python (riduce uso CPU)
  senza alterare la logica.
- Avvia l'identica pipeline di main.py (JarvisLive + JarvisUI).
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
    """Imposta priorita' BelowNormal del processo per non saturare la CPU.
    No-op se psutil non e' disponibile o su sistemi non Windows."""
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
    print("  JARVIS — Avvio COMPLETO (GUI + voce + tool calling)")
    print("=" * 60)

    # Importa DOPO l'installazione delle dipendenze.
    from main import main as jarvis_main
    jarvis_main()


if __name__ == "__main__":
    main()

# main_headless.py
# Avvio QUASI / MARK XXXIX-OR senza GUI.
#
# - Riusa lo stesso JarvisLive di main.py (audio + tool calling + memoria).
# - Sostituisce JarvisUI con un adattatore "console" che espone gli stessi
#   metodi minimi (write_log, set_state, muted, ecc.) ma stampa su stdout.
# - Tutto il resto (send_message, web_search, dashboard messaggi in
#   modalita' CLI, ecc.) funziona come nella modalita' GUI.
#
# Avvio:
#     python main_headless.py
# o tramite start_quasi_headless.bat (su Windows).

from __future__ import annotations
import asyncio
import json
import sys
import threading
import time
from pathlib import Path


def _base() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


API_CONFIG_PATH = _base() / "config" / "api_keys.json"


def _ensure_api_key() -> None:
    """Verifica/richiede la chiave Gemini in modalita' headless."""
    cfg = {}
    if API_CONFIG_PATH.is_file():
        try:
            cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    if cfg.get("gemini_api_key"):
        return
    print("\n[QUASI headless] Chiave Gemini non trovata.")
    k = input("Inserisci la tua GEMINI API KEY (https://aistudio.google.com): ").strip()
    if not k:
        print("Chiave vuota, esco.")
        sys.exit(1)
    cfg["gemini_api_key"] = k
    API_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    API_CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    print("Chiave salvata in", API_CONFIG_PATH)


class ConsoleUI:
    """Stub minimale che imita l'interfaccia di JarvisUI per il backend.
    Tutti i metodi che la GUI usa per disegnare diventano no-op o print."""

    def __init__(self) -> None:
        self.muted = False
        self.current_file: str | None = None
        self._state = "IDLE"
        self._ready_event = threading.Event()
        # API key gia' verificata da _ensure_api_key()
        self._ready_event.set()

    # --- API attese da main.JarvisLive ---------------------------------
    def wait_for_api_key(self) -> None:
        self._ready_event.wait()

    def write_log(self, line: str) -> None:
        try:
            print(line, flush=True)
        except Exception:
            pass

    def set_state(self, state: str) -> None:
        self._state = state
        print(f"[state] {state}", flush=True)

    # WhatsApp / overlay: in headless non c'e' nulla da mostrare, no-op.
    def show_whatsapp_overlay(self, *a, **kw):  print("[wa] overlay (headless: no-op)")
    def show_chat_overlay(self, *a, **kw):      print("[chat] overlay (headless: no-op)")
    def show_stats_overlay(self, *a, **kw):     print("[stats] overlay (headless: no-op)")
    def set_on_whatsapp_new_message(self, *a, **kw): pass
    def return_home(self, *a, **kw): pass

    # Audio: non serve in headless puro audio (delegato a sounddevice).
    def play_sound(self, *a, **kw): pass


def main() -> None:
    print("=" * 60)
    print("  QUASI / MARK XXXIX-OR — modalita' HEADLESS (no GUI)")
    print("=" * 60)
    _ensure_api_key()

    # Importa JarvisLive DOPO aver garantito la api key.
    from main import JarvisLive

    ui = ConsoleUI()

    # Collega la mappa al "ui" finto cosi' eventuali chiamate non crashano.
    try:
        from actions.jarvis_map import set_ui_reference
        set_ui_reference(ui)
    except Exception:
        pass

    jarvis = JarvisLive(ui)

    def runner():
        try:
            asyncio.run(jarvis.run())
        except KeyboardInterrupt:
            print("\n[QUASI] shutdown")

    t = threading.Thread(target=runner, daemon=True)
    t.start()

    print("\n[QUASI] In ascolto. Parla nel microfono. Ctrl+C per uscire.\n")
    print("Comandi console rapidi: 'mute', 'unmute', 'dashboard', 'quit'")

    try:
        while True:
            try:
                line = input().strip().lower()
            except EOFError:
                time.sleep(1.0)
                continue
            if not line:
                continue
            if line in ("quit", "exit", "q"):
                print("[QUASI] uscita.")
                break
            elif line == "mute":
                ui.muted = True
                print("[QUASI] microfono mutato.")
            elif line == "unmute":
                ui.muted = False
                print("[QUASI] microfono attivo.")
            elif line == "dashboard":
                from actions.send_dashboard import open_dashboard
                open_dashboard(prefer_gui=False)
            else:
                print(f"[QUASI] comando sconosciuto: {line}")
    except KeyboardInterrupt:
        print("\n[QUASI] interrotto.")


if __name__ == "__main__":
    main()

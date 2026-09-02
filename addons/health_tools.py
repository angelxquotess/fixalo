"""addons/health_tools.py — benessere: 20-20-20, acqua, stretching, postura."""
from __future__ import annotations

import itertools
import threading

from .core import notify

_running: dict[str, threading.Event] = {}


def _loop(name: str, interval_s: int, message: str) -> None:
    stop = _running.setdefault(name, threading.Event())
    while not stop.wait(interval_s):
        notify("JARVIS Benessere", message)


def eye_rest_start(minutes: int = 20) -> str:
    """Regola 20-20-20: ogni 20 min guarda lontano per 20 secondi."""
    eye_rest_stop()
    t = threading.Thread(
        target=_loop,
        args=("eye", int(minutes) * 60,
              "Guarda un punto a 6 metri per 20 secondi."),
        daemon=True)
    t.start()
    return f"Promemoria occhi attivo ogni {minutes} minuti."

def eye_rest_stop() -> str:
    ev = _running.pop("eye", None)
    if ev:
        ev.set()
    return "Promemoria occhi fermato."

def water_reminder_start(minutes: int = 45) -> str:
    water_reminder_stop()
    t = threading.Thread(
        target=_loop,
        args=("water", int(minutes) * 60, "Bevi un bicchiere d'acqua."),
        daemon=True)
    t.start()
    return f"Promemoria idratazione ogni {minutes} minuti."

def water_reminder_stop() -> str:
    ev = _running.pop("water", None)
    if ev:
        ev.set()
    return "Promemoria acqua fermato."

def stretch_reminder_start(minutes: int = 60) -> str:
    stretch_reminder_stop()
    t = threading.Thread(
        target=_loop,
        args=("stretch", int(minutes) * 60,
              "Alzati e fai stretching per 2 minuti."),
        daemon=True)
    t.start()
    return f"Promemoria stretching ogni {minutes} minuti."

def stretch_reminder_stop() -> str:
    ev = _running.pop("stretch", None)
    if ev:
        ev.set()
    return "Promemoria stretching fermato."

def posture_check() -> str:
    tips = [
        "Schiena dritta, spalle rilassate.",
        "Schermo all'altezza degli occhi.",
        "Piedi ben appoggiati a terra.",
        "Polsi dritti sulla tastiera.",
        "Gomiti a circa 90 gradi.",
    ]
    import random
    return random.choice(tips)


def stop_all() -> str:
    for name in list(_running):
        _running.pop(name).set()
    return "Tutti i promemoria benessere fermati."

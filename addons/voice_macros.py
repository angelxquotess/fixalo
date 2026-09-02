"""addons/voice_macros.py — scorciatoie vocali parola-per-parola.

Una macro = frase trigger ESATTA -> sequenza di step addon.
Salvate in addons/data/macros.json. Esempio:

    trigger: "modalità lavoro"
    steps:   [{"addon": "pomodoro_start", "params": {"work_min": 50}},
              {"addon": "eye_rest_start", "params": {}},
              {"addon": "note_add", "params": {"text": "Inizio sessione {input}"}}]

Fast-path: main.py chiama try_fast_path() ad ogni frase riconosciuta;
se il match e' esatto (ignorando maiuscole/punteggiatura) la sequenza
parte SUBITO, senza aspettare l'interpretazione del modello.
Placeholder "{input}" nei parametri = la frase pronunciata.
"""
from __future__ import annotations

import re
import time

from .core import load_store, save_store

_last_run: dict[str, float] = {}
DEDUP_SECONDS = 10


def _norm(text: str) -> str:
    import unicodedata
    t = (text or "").lower().strip()
    # rimuove gli accenti: la trascrizione vocale puo' variare ("modalità"
    # vs "modalita") e il match deve restare parola-per-parola affidabile
    t = "".join(c for c in unicodedata.normalize("NFD", t)
                if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^\w\s']", "", t)
    return re.sub(r"\s+", " ", t).strip()


def macro_create(trigger: str, steps_json: str) -> str:
    import json
    trigger_n = _norm(trigger)
    if not trigger_n:
        return "Trigger non valido."
    try:
        steps = json.loads(steps_json) if isinstance(steps_json, str) else steps_json
    except Exception as e:
        return f"steps_json non valido: {e}"
    if not isinstance(steps, list) or not steps:
        return "La macro deve avere almeno uno step."
    for s in steps:
        if not isinstance(s, dict) or "addon" not in s:
            return "Ogni step deve essere {\"addon\": nome, \"params\": {...}}."
    macros = load_store("macros", {})
    macros[trigger_n] = steps
    save_store("macros", macros)
    return (f"Scorciatoia '{trigger_n}' creata con {len(steps)} step. "
            f"Dillo esattamente cosi' per lanciarla.")


def macro_delete(trigger: str) -> str:
    macros = load_store("macros", {})
    if _norm(trigger) in macros:
        del macros[_norm(trigger)]
        save_store("macros", macros)
        return f"Scorciatoia '{trigger}' eliminata."
    return f"Nessuna scorciatoia chiamata '{trigger}'."


def macro_list() -> list[dict]:
    macros = load_store("macros", {})
    return [{"trigger": k, "steps": [s.get("addon", "?") for s in v]}
            for k, v in macros.items()] or "Nessuna scorciatoia definita."


def _run_steps(trigger_n: str, steps: list, spoken_text: str) -> str:
    from .voice_bridge import execute_addon
    results = []
    for s in steps:
        name = s.get("addon", "")
        params = {k: (str(v).replace("{input}", spoken_text) if isinstance(v, str) else v)
                  for k, v in (s.get("params") or {}).items()}
        tool = name if name.startswith("addon_") else f"addon_{name}"
        results.append(str(execute_addon(tool, params)))
    return " | ".join(results)


def macro_run(trigger: str) -> str:
    """Esecuzione via tool vocale (il modello la chiama)."""
    trigger_n = _norm(trigger)
    macros = load_store("macros", {})
    if trigger_n not in macros:
        return (f"Nessuna scorciatoia '{trigger_n}'. "
                f"Disponibili: {', '.join(macros) or 'nessuna'}")
    # dedup: se il fast-path l'ha appena eseguita, non ripetere
    if time.time() - _last_run.get(trigger_n, 0) < DEDUP_SECONDS:
        return f"Scorciatoia '{trigger_n}' gia' eseguita ora."
    _last_run[trigger_n] = time.time()
    return _run_steps(trigger_n, macros[trigger_n], trigger)


def try_fast_path(spoken_text: str, jarvis=None) -> bool:
    """Match ESATTO parola-per-parola -> esecuzione immediata locale.
    Chiamato da main._receive_audio ad ogni frase riconosciuta.
    Ritorna True se una macro e' stata eseguita."""
    trigger_n = _norm(spoken_text)
    if not trigger_n:
        return False
    macros = load_store("macros", {})
    if trigger_n not in macros:
        return False
    if time.time() - _last_run.get(trigger_n, 0) < DEDUP_SECONDS:
        return True
    _last_run[trigger_n] = time.time()

    result = _run_steps(trigger_n, macros[trigger_n], spoken_text)
    if jarvis is not None:
        try:
            jarvis.write_log(f"SYS: scorciatoia '{trigger_n}' -> {result[:200]}")
        except Exception:
            pass
    print(f"[JARVIS] ⚡ macro '{trigger_n}' eseguita: {result[:120]}")
    return True

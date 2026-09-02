"""addons/productivity.py — note, pomodoro, abitudini, spese, timer, focus."""
from __future__ import annotations

import time
from datetime import datetime

from .core import (load_store, save_store, notify, run_later, now_iso)

# ---------------------------------------------------------------- note
def note_add(text: str) -> str:
    notes = load_store("notes", [])
    notes.append({"ts": now_iso(), "text": text})
    save_store("notes", notes)
    return f"Nota salvata ({len(notes)} totali)."

def note_list(n: int = 10) -> list[dict]:
    return load_store("notes", [])[-n:]

def note_search(query: str) -> list[dict]:
    q = query.lower()
    return [x for x in load_store("notes", []) if q in x["text"].lower()]

def note_clear() -> str:
    save_store("notes", [])
    return "Note cancellate."

# ------------------------------------------------------------- pomodoro
_pomodoro_running = False

def pomodoro_start(work_min: int = 25, break_min: int = 5) -> str:
    global _pomodoro_running
    if _pomodoro_running:
        return "Pomodoro gia' attivo."
    _pomodoro_running = True

    def _cycle():
        global _pomodoro_running
        notify("JARVIS Pomodoro", f"Lavora per {work_min} minuti.")
        run_later(work_min * 60, lambda: (
            notify("JARVIS Pomodoro", f"Pausa di {break_min} minuti!"),
            run_later(break_min * 60, lambda: _cycle() if _pomodoro_running else None)
        ))
    _cycle()
    return f"Pomodoro avviato: {work_min} min lavoro / {break_min} min pausa."

def pomodoro_stop() -> str:
    global _pomodoro_running
    _pomodoro_running = False
    return "Pomodoro fermato."

# ------------------------------------------------------------- abitudini
def habit_mark(name: str) -> str:
    habits = load_store("habits", {})
    today = datetime.now().strftime("%Y-%m-%d")
    days = set(habits.get(name, []))
    days.add(today)
    habits[name] = sorted(days)
    save_store("habits", habits)
    streak = 0
    d = datetime.now().date()
    from datetime import timedelta
    while d.strftime("%Y-%m-%d") in days:
        streak += 1
        d -= timedelta(days=1)
    return f"Abitudine '{name}' segnata. Streak: {streak} giorni."

def habit_stats() -> dict:
    return load_store("habits", {})

# ---------------------------------------------------------------- spese
def expense_add(amount: float, category: str = "altro", note: str = "") -> str:
    exp = load_store("expenses", [])
    exp.append({"ts": now_iso(), "amount": float(amount),
                "category": category, "note": note})
    save_store("expenses", exp)
    return f"Spesa di {amount:.2f} EUR registrata ({category})."

def expense_summary() -> dict:
    exp = load_store("expenses", [])
    tot = {}
    for e in exp:
        tot[e["category"]] = round(tot.get(e["category"], 0) + e["amount"], 2)
    return {"total": round(sum(e["amount"] for e in exp), 2), "by_category": tot}

# ----------------------------------------------------------- timer/allarme
def set_timer(seconds: int, message: str = "Timer scaduto!") -> str:
    run_later(seconds, lambda: notify("JARVIS Timer", message))
    m, s = divmod(int(seconds), 60)
    return f"Timer impostato: {m} min {s} sec."

def set_alarm(hh: int, mm: int, message: str = "Sveglia!") -> str:
    now = datetime.now()
    target = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    if target <= now:
        from datetime import timedelta
        target += timedelta(days=1)
    delay = (target - now).total_seconds()
    run_later(delay, lambda: notify("JARVIS Sveglia", message))
    return f"Sveglia alle {hh:02d}:{mm:02d} (tra {int(delay//60)} minuti)."

def stopwatch_start() -> str:
    save_store("stopwatch", {"start": time.time()})
    return "Cronometro avviato."

def stopwatch_read() -> str:
    sw = load_store("stopwatch", None)
    if not sw:
        return "Cronometro non avviato."
    el = time.time() - sw["start"]
    return f"Tempo trascorso: {int(el//60)} min {el%60:.1f} sec."

# ------------------------------------------------------------- promemoria
def remind_in(minutes: int, text: str) -> str:
    run_later(int(minutes) * 60, lambda: notify("JARVIS Promemoria", text))
    return f"Te lo ricordo tra {minutes} minuti."

# --------------------------------------------------------- meeting notes
def meeting_log(text: str) -> str:
    notes = load_store("meeting", [])
    notes.append({"ts": now_iso(), "text": text})
    save_store("meeting", notes)
    return f"[{datetime.now().strftime('%H:%M')}] annotato."

def meeting_export() -> str:
    notes = load_store("meeting", [])
    return "\n".join(f"[{n['ts'][:16]}] {n['text']}" for n in notes)

# ------------------------------------------------------------- focus mode
def focus_list_add(site: str) -> str:
    lst = load_store("focus_sites", [])
    if site not in lst:
        lst.append(site)
        save_store("focus_sites", lst)
    return f"'{site}' aggiunto alla lista distrazioni."

def focus_sites() -> list:
    return load_store("focus_sites", [])

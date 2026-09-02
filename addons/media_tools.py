"""addons/media_tools.py — schermo, audio, colori, clipboard."""
from __future__ import annotations

import time
from pathlib import Path

from .core import BASE_DIR

# -------------------------------------------------------------- screenshot
def screenshot(dest_dir: str | None = None) -> str:
    import mss
    import mss.tools
    d = Path(dest_dir) if dest_dir else (BASE_DIR / "addons" / "data" / "shots")
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"shot_{time.strftime('%Y%m%d_%H%M%S')}.png"
    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[0])
        mss.tools.to_png(shot.rgb, shot.size, output=str(out))
    return str(out)

# -------------------------------------------------------------- color picker
def pixel_color(x: int, y: int) -> dict:
    import mss
    with mss.mss() as sct:
        shot = sct.grab({"left": int(x), "top": int(y), "width": 1, "height": 1})
        r, g, b = shot.pixel(0, 0)[:3]
    return {"rgb": (r, g, b), "hex": f"#{r:02x}{g:02x}{b:02x}"}

# ---------------------------------------------------------- audio recorder
def record_audio(seconds: int = 10, dest: str | None = None) -> str:
    import wave
    import sounddevice as sd
    sr = 16000
    data = sd.rec(int(seconds) * sr, samplerate=sr, channels=1, dtype="int16")
    sd.wait()
    out = dest or str(BASE_DIR / "addons" / "data" /
                      f"rec_{time.strftime('%Y%m%d_%H%M%S')}.wav")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())
    return out

# -------------------------------------------------------------- clipboard
def clipboard_get() -> str:
    try:
        import pyperclip
        return pyperclip.paste()
    except Exception as e:
        return f"Errore clipboard: {e}"

def clipboard_set(text: str) -> str:
    try:
        import pyperclip
        pyperclip.copy(text)
        return "Copiato negli appunti."
    except Exception as e:
        return f"Errore clipboard: {e}"

def clipboard_history_push() -> str:
    """Salva il contenuto attuale della clipboard nello storico."""
    from .core import load_store, save_store, now_iso
    txt = clipboard_get()
    if not txt or txt.startswith("Errore"):
        return "Clipboard vuota."
    hist = load_store("clipboard_hist", [])
    if hist and hist[-1]["text"] == txt:
        return "Gia' nello storico."
    hist.append({"ts": now_iso(), "text": txt[:2000]})
    save_store("clipboard_hist", hist[-100:])
    return f"Salvato ({len(hist)} voci nello storico)."

def clipboard_history(n: int = 5) -> list[dict]:
    from .core import load_store
    return load_store("clipboard_hist", [])[-n:]

# ------------------------------------------------------------ typing macro
def type_text(text: str, interval: float = 0.02) -> str:
    import pyautogui
    time.sleep(1)  # tempo per focuсare la finestra target
    pyautogui.typewrite(text, interval=interval) if text.isascii() else None
    if not text.isascii():
        import pyperclip
        old = pyperclip.paste()
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        pyperclip.copy(old)
    return "Testo digitato."

# --------------------------------------------------------------- autogui
def mouse_position() -> tuple[int, int]:
    import pyautogui
    p = pyautogui.position()
    return (p.x, p.y)

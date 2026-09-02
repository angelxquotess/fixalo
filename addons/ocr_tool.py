"""addons/ocr_tool.py — OCR dello schermo: legge il testo da uno screenshot.

Strategia a cascata:
1. pytesseract (offline, richiede Tesseract installato su Windows)
2. Vision via or_client (OpenRouter, modelli free) come fallback
"""
from __future__ import annotations


def ocr_screenshot(lang: str = "ita+eng") -> str:
    from .media_tools import screenshot

    path = screenshot()

    # 1) Tesseract offline
    try:
        import pytesseract
        from PIL import Image
        txt = pytesseract.image_to_string(Image.open(path), lang=lang)
        txt = " ".join(txt.split())
        if txt:
            return txt
        return "Nessun testo rilevato nello screenshot."
    except ImportError:
        pass  # pytesseract non installato -> fallback vision
    except Exception as e:
        err = str(e).lower()
        if "tesseract" not in err:  # errore PIL/altro: prova comunque il fallback
            pass

    # 2) Fallback: vision model via or_client (richiede rete + chiave OpenRouter)
    try:
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from or_client import OpenRouterClient
        return OpenRouterClient().vision_from_file(
            "Trascrivi TUTTO il testo visibile in questo screenshot, "
            "in italiano se presente. Rispondi solo con il testo letto.",
            path,
        )
    except Exception as e:
        return (
            "OCR non disponibile. Installa Tesseract "
            "(https://github.com/UB-Mannheim/tesseract/wiki) e "
            "'pip install pytesseract', oppure configura openrouter_api_key. "
            f"Dettaglio: {e}"
        )


def ocr_region(x: int, y: int, w: int, h: int, lang: str = "ita+eng") -> str:
    """OCR di una regione dello schermo."""
    import time
    import mss
    import mss.tools
    from pathlib import Path

    out = Path(__file__).resolve().parent / "data" / f"ocr_{int(time.time())}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    with mss.mss() as sct:
        shot = sct.grab({"left": int(x), "top": int(y),
                         "width": int(w), "height": int(h)})
        mss.tools.to_png(shot.rgb, shot.size, output=str(out))
    try:
        import pytesseract
        from PIL import Image
        txt = pytesseract.image_to_string(Image.open(out), lang=lang)
        return " ".join(txt.split()) or "Nessun testo rilevato."
    except Exception as e:
        return f"OCR regione non disponibile: {e}"

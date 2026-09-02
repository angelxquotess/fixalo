"""addons/qr_tool.py — QR code: generazione e lettura da schermo/file.

Generazione: pacchetto `qrcode` (puro Python + Pillow, gia' presente).
Lettura: OpenCV QRCodeDetector — opencv-python e' GIA' nei requirements
di JARVIS, quindi nessuna dipendenza nativa extra (niente zbar).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

QR_DIR = Path(__file__).resolve().parent / "data" / "qr"


def qr_create(data: str, filename: str | None = None, show: bool = True) -> str:
    """Genera un QR code PNG e (su Windows) lo apre subito a schermo."""
    data = (data or "").strip()
    if not data:
        return "Nessun dato per il QR code."
    if isinstance(show, str):
        show = show.strip().lower() not in ("no", "false", "0", "n")
    try:
        import qrcode
    except ImportError:
        return "Pacchetto 'qrcode' mancante: pip install qrcode"

    QR_DIR.mkdir(parents=True, exist_ok=True)
    name = filename or f"qr_{int(time.time())}"
    if not name.lower().endswith(".png"):
        name += ".png"
    out = QR_DIR / name

    img = qrcode.make(data)
    img.save(str(out))

    if show:
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(out))
            elif sys.platform == "darwin":
                os.system(f'open "{out}"')
            else:
                os.system(f'xdg-open "{out}" &')
        except Exception:
            pass
    return f"QR code creato: {out}"


def _decode_image_bgr(img) -> list[str]:
    import cv2
    det = cv2.QRCodeDetector()
    results: list[str] = []
    try:
        ok, decoded, _points, _ = det.detectAndDecodeMulti(img)
        if ok:
            results = [d for d in decoded if d]
    except Exception:
        pass
    if not results:
        single, _pts, _ = det.detectAndDecode(img)
        if single:
            results = [single]
    return results


def qr_read_screen() -> str:
    """Cattura lo schermo e decodifica eventuali QR code visibili."""
    try:
        import cv2
        import numpy as np
        import mss
    except ImportError as e:
        return f"Dipendenza mancante per la lettura QR: {e}"

    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[0])
        img = np.frombuffer(shot.bgra, dtype=np.uint8).reshape(
            shot.height, shot.width, 4)[:, :, :3]

    found = _decode_image_bgr(img)
    if not found:
        return "Nessun QR code trovato sullo schermo."
    return "QR letto: " + " | ".join(found)


def qr_read_file(path: str) -> str:
    """Decodifica un QR code da un file immagine."""
    try:
        import cv2
    except ImportError as e:
        return f"Dipendenza mancante: {e}"
    img = cv2.imread(str(path))
    if img is None:
        return f"Immagine non leggibile: {path}"
    found = _decode_image_bgr(img)
    if not found:
        return "Nessun QR code trovato nell'immagine."
    return "QR letto: " + " | ".join(found)

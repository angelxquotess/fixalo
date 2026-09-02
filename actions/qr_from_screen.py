"""
qr_from_screen.py — Genera un QR code a partire dal link che JARVIS vede
sullo schermo.

Flusso:
  1) Cattura lo schermo (mss).
  2) Estrae eventuali URL con OCR (pytesseract) o, in mancanza, con visione AI
     (Gemini) se disponibile.
  3) Se e' passato `url` come parametro, salta la scansione.
  4) Genera un PNG QR con la libreria `qrcode`.
  5) Mostra il QR in una finestra PyQt cinematica sopra la UI JARVIS.

Il tool viene dichiarato da main.py come `qr_from_screen`.
"""
from __future__ import annotations

import io
import os
import re
import sys
import tempfile
import threading
from pathlib import Path

_URL_REGEX = re.compile(
    r"(https?://[^\s\"'<>()\[\]{}]+|www\.[^\s\"'<>()\[\]{}]+|"
    r"[a-zA-Z0-9][a-zA-Z0-9\-]{1,63}\.(?:com|it|org|net|io|dev|app|ai|co|"
    r"gov|edu|info|tv|me|xyz)(?:/[^\s\"'<>()\[\]{}]*)?)"
)


def _capture_screen_png() -> bytes | None:
    try:
        import mss
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[1])  # primary monitor
            from PIL import Image
            img = Image.frombytes("RGB", shot.size, shot.rgb)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
    except Exception as e:
        print(f"[QR] capture failed: {e}")
        return None


def _ocr_extract_url(png_bytes: bytes) -> str | None:
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(png_bytes))
        text = pytesseract.image_to_string(img)
        m = _URL_REGEX.search(text)
        if m:
            u = m.group(1)
            if not u.startswith("http"):
                u = "https://" + u
            return u
    except Exception as e:
        print(f"[QR] OCR failed / not available: {e}")
    return None


def _ai_extract_url(png_bytes: bytes) -> str | None:
    """Fallback: chiede a Gemini di estrarre l'URL dallo screenshot."""
    try:
        import json
        from pathlib import Path as _P
        cfg = _P(__file__).resolve().parent.parent / "config" / "api_keys.json"
        api_key = json.loads(cfg.read_text(encoding="utf-8"))["gemini_api_key"]
        from google import genai
        from google.genai import types as gtypes
        client = genai.Client(api_key=api_key)
        r = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                gtypes.Part.from_bytes(data=png_bytes, mime_type="image/png"),
                "Guarda questo screenshot. Restituisci SOLO l'URL principale "
                "visibile (barra indirizzo o link a schermo). "
                "Rispondi SOLO con l'URL, senza altro testo. "
                "Se non c'e' alcun URL, rispondi con NONE.",
            ],
        )
        txt = (r.text or "").strip()
        if not txt or txt.upper() == "NONE":
            return None
        m = _URL_REGEX.search(txt)
        if m:
            u = m.group(1)
            if not u.startswith("http"):
                u = "https://" + u
            return u
    except Exception as e:
        print(f"[QR] AI extract failed: {e}")
    return None


def _make_qr_png(url: str) -> str:
    """Genera un PNG del QR e ritorna il path del file su disco."""
    import qrcode
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#00e5ff", back_color="#02070c").convert("RGB")
    out = Path(tempfile.gettempdir()) / "jarvis_last_qr.png"
    img.save(out)
    return str(out)


def _show_qr_window(png_path: str, url: str, player=None):
    """Mostra il QR in una finestra PyQt6 cinematica (HUD)."""
    try:
        from PyQt6.QtCore import Qt, QTimer
        from PyQt6.QtGui import QPixmap, QFont
        from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget, QPushButton

        def _show():
            w = QWidget()
            w.setWindowTitle("JARVIS · QR SCAN")
            w.setStyleSheet(
                "background: #02070c; color: #9df3ff; border: 1px solid #10486b;"
            )
            w.setMinimumSize(360, 460)
            lay = QVBoxLayout(w)
            lay.setContentsMargins(18, 18, 18, 18)
            lay.setSpacing(10)

            title = QLabel("◈  QR GENERATO DA SCHERMATA")
            title.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
            title.setStyleSheet("color: #00e5ff; background: transparent;")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(title)

            img_lbl = QLabel()
            px = QPixmap(png_path).scaled(
                300, 300,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            img_lbl.setPixmap(px)
            img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img_lbl.setStyleSheet(
                "background: #02070c; border: 1px solid #10486b; padding: 6px;"
            )
            lay.addWidget(img_lbl)

            url_lbl = QLabel(url)
            url_lbl.setFont(QFont("Courier New", 8))
            url_lbl.setStyleSheet("color: #63c4d8; background: transparent;")
            url_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            url_lbl.setWordWrap(True)
            lay.addWidget(url_lbl)

            close_btn = QPushButton("CHIUDI")
            close_btn.setFixedHeight(30)
            close_btn.setStyleSheet(
                "QPushButton { background: transparent; color: #00e5ff; "
                "border: 1px solid #10486b; border-radius: 3px; }"
                "QPushButton:hover { color: #e2fbff; border: 1px solid #00e5ff; }"
            )
            close_btn.clicked.connect(w.close)
            lay.addWidget(close_btn)

            w.show()
            # Keep a reference to prevent GC
            if player is not None:
                setattr(player, "_last_qr_window", w)

        # Deve essere invocato nel main thread Qt.
        if player is not None and hasattr(player, "_map_sig"):
            # sfrutta la thread-safety di Qt: usiamo QTimer.singleShot con lambda
            QTimer.singleShot(0, _show)
        else:
            _show()
    except Exception as e:
        print(f"[QR] Cannot show QR window: {e}")


def qr_from_screen(parameters: dict = None, player=None, **kwargs) -> str:
    params = parameters or {}
    url = (params.get("url") or "").strip()

    if not url:
        png = _capture_screen_png()
        if not png:
            return "Impossibile catturare lo schermo."
        # 1) OCR veloce
        url = _ocr_extract_url(png) or ""
        # 2) fallback AI
        if not url:
            url = _ai_extract_url(png) or ""

    if not url:
        msg = "Nessun URL riconosciuto sullo schermo, signore."
        if player:
            player.write_log(f"[QR] {msg}")
        return msg

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        png_path = _make_qr_png(url)
    except Exception as e:
        return f"Errore generazione QR: {e}"

    _show_qr_window(png_path, url, player=player)
    if player:
        try:
            player.write_log(f"[QR] {url}")
        except Exception:
            pass
    return f"QR generato per {url}. Mostrato a schermo."

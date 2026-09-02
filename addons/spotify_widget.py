"""addons/spotify_widget.py — mini player Spotify nella finestra JARVIS.

Mostra brano in riproduzione (titolo/artista dalla window title di
Spotify su Windows), copertina via oEmbed (con cache), e controlli
⏮ ⏯ ⏭ via i WM_APPCOMMAND gia' esistenti in spotify_api.py.
Polling ogni 5s, solo quando la finestra e' visibile (CPU-friendly).
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

_CACHE_DIR = Path(__file__).resolve().parent / "data" / "covers"


def get_now_playing() -> dict | None:
    """Titolo finestra Spotify su Windows: 'Artista - Titolo' se in play,
    'Spotify' / 'Spotify Free' se in pausa o chiusa."""
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes
        from ctypes import wintypes
        from spotify_api import _find_all_spotify_hwnds

        for hwnd in _find_all_spotify_hwnds(include_invisible=True):
            n = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if n <= 0:
                continue
            buf = ctypes.create_unicode_buffer(n + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, n + 1)
            title = (buf.value or "").strip()
            if not title or title.lower().startswith("spotify"):
                return {"name": "", "artist": "", "playing": False}
            if " - " in title:
                artist, name = title.split(" - ", 1)
                return {"name": name.strip(), "artist": artist.strip(),
                        "playing": True}
            return {"name": title, "artist": "", "playing": True}
    except Exception:
        pass
    return None


def _fetch_cover(name: str, artist: str) -> str | None:
    """Copertina via search_track + oEmbed (thumbnail_url), con cache disco."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        key = f"{artist}-{name}".lower().replace(" ", "_")[:60]
        cached = _CACHE_DIR / f"{key}.jpg"
        if cached.is_file():
            return str(cached)
        import requests
        from spotify_api import search_track
        track = search_track(f"{name} {artist}".strip())
        if not track or "track/" not in track.get("uri", ""):
            return None
        tid = track["uri"].split("track/")[-1]
        r = requests.get(
            "https://open.spotify.com/oembed",
            params={"url": f"https://open.spotify.com/track/{tid}"},
            timeout=8)
        thumb = r.json().get("thumbnail_url")
        if not thumb:
            return None
        img = requests.get(thumb, timeout=8).content
        cached.write_bytes(img)
        return str(cached)
    except Exception:
        return None


def media_cmd(action: str) -> str:
    """action: play_pause | next | prev"""
    try:
        from spotify_api import (_send_appcommand,
                                 APPCOMMAND_MEDIA_NEXTTRACK,
                                 APPCOMMAND_MEDIA_PLAY_PAUSE,
                                 APPCOMMAND_MEDIA_PREVIOUSTRACK)
        cmd = {"play_pause": APPCOMMAND_MEDIA_PLAY_PAUSE,
               "next": APPCOMMAND_MEDIA_NEXTTRACK,
               "prev": APPCOMMAND_MEDIA_PREVIOUSTRACK}[action]
        ok = _send_appcommand(cmd)
        return "OK" if ok else "Spotify non trovato."
    except Exception as e:
        return f"Errore: {e}"


class MiniPlayer(QWidget):
    _track_sig = pyqtSignal(object)   # dict | None
    _cover_sig = pyqtSignal(str)      # path immagine

    def __init__(self, parent=None):
        super().__init__(parent)
        from ui import C
        self._track_key = ""
        self.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER};"
            f"border-radius: 4px;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 5, 6, 5)
        lay.setSpacing(4)

        hdr = QLabel("▸ SPOTIFY")
        hdr.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.NEON2}; background: transparent; border: none;")
        lay.addWidget(hdr)

        row = QHBoxLayout()
        row.setSpacing(6)
        self._cover = QLabel("♪")
        self._cover.setFixedSize(52, 52)
        self._cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover.setFont(QFont("Courier New", 16))
        self._cover.setStyleSheet(
            f"color: {C.PRI_DIM}; background: {C.BAR_BG};"
            f"border: 1px solid {C.BORDER_A}; border-radius: 4px;")
        row.addWidget(self._cover)

        tcol = QVBoxLayout()
        tcol.setSpacing(1)
        self._name = QLabel("—")
        self._name.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._name.setStyleSheet(f"color: {C.WHITE}; background: transparent; border: none;")
        self._name.setWordWrap(True)
        self._artist = QLabel("non in riproduzione")
        self._artist.setFont(QFont("Courier New", 7))
        self._artist.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
        self._artist.setWordWrap(True)
        tcol.addWidget(self._name)
        tcol.addWidget(self._artist)
        tcol.addStretch(1)
        row.addLayout(tcol, stretch=1)
        lay.addLayout(row)

        ctl = QHBoxLayout()
        ctl.setSpacing(4)
        for label, action in [("⏮", "prev"), ("⏯", "play_pause"), ("⏭", "next")]:
            b = QPushButton(label)
            b.setFixedHeight(22)
            b.setFont(QFont("Courier New", 9))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.PRI};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
                QPushButton:hover {{
                    color: {C.DARK}; background: {C.PRI};
                }}
            """)
            b.clicked.connect(lambda _=False, a=action: self._cmd(a))
            ctl.addWidget(b)
        lay.addLayout(ctl)

        self._track_sig.connect(self._apply_track)
        self._cover_sig.connect(self._apply_cover)

        self._poll_tmr = QTimer(self)
        self._poll_tmr.timeout.connect(self._poll)
        self._poll_tmr.start(5000)
        QTimer.singleShot(1200, self._poll)

    # ------------------------------------------------------------------
    def _cmd(self, action: str):
        threading.Thread(target=media_cmd, args=(action,), daemon=True).start()
        QTimer.singleShot(900, self._poll)

    def _poll(self):
        if not self.isVisible():
            return  # CPU-friendly: niente polling a pannello nascosto

        def _work():
            info = get_now_playing()
            self._track_sig.emit(info)
            if info and info.get("name"):
                key = f"{info.get('artist')}|{info.get('name')}"
                if key != self._track_key:
                    self._track_key = key
                    cover = _fetch_cover(info["name"], info.get("artist", ""))
                    if cover:
                        self._cover_sig.emit(cover)
        threading.Thread(target=_work, daemon=True).start()

    def _apply_track(self, info):
        if not info:
            self._name.setText("—")
            self._artist.setText("Spotify non rilevato")
            return
        if not info.get("name"):
            self._name.setText("‖ pausa")
            self._artist.setText("Spotify aperto")
            return
        self._name.setText(info["name"])
        self._artist.setText(info.get("artist") or "")

    def _apply_cover(self, path: str):
        px = QPixmap(path)
        if not px.isNull():
            self._cover.setPixmap(px.scaled(
                52, 52,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation))

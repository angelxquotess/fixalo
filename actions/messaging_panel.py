"""
actions/messaging_panel.py
==========================

Fase 5 — "Apri WhatsApp" / "Apri Instagram" ora aprono una piccola
tendina (floating window) che mostra WhatsApp Web / Instagram Direct.

* La tendina è un QWidget frameless, always-on-top, ridimensionabile.
* Include un QWebEngineView che carica web.whatsapp.com o instagram.com/direct/inbox
* Sopra al webview mostra un badge con il numero di messaggi non letti.
* Un piccolo poller JS legge il DOM ogni ~4 secondi ed emette un segnale
  quando arriva un nuovo messaggio → il MessagingPanelManager mostra un
  popup toast "Nuovo messaggio da X — vuoi rispondere?" con bottone
  Si/No; se l'utente clicca Sì lancia lo speak "Cosa vuoi rispondere?"
  e chiama la callback di reply (che poi passa da actions/send_message).

Il manager è un singleton — la stessa istanza viene riutilizzata per
tutte le chiamate.  Ogni piattaforma ha la sua tendina indipendente.

USATO DA:
    * actions/open_app.py    (intercetta 'whatsapp' / 'instagram')
    * actions/check_messages (via callback opzionale on_new_message)
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal, QPoint
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
    QSizeGrip,
)

try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    _WEB_OK = True
except Exception:  # pragma: no cover
    QWebEngineView = None  # type: ignore
    _WEB_OK = False


_PLATFORMS = {
    "whatsapp": {
        "url": "https://web.whatsapp.com/",
        "title": "WhatsApp",
        "color": "#25D366",
        # DOM heuristic: WA renders unread badges as spans with aria-label
        # like "3 messaggi non letti"
        "js_unread": (
            "(() => {"
            "  try {"
            "    const badges = document.querySelectorAll('[aria-label*=\"non lett\"], [aria-label*=\"unread\"]');"
            "    let n = 0; let last = '';"
            "    badges.forEach(b => {"
            "      const m = (b.getAttribute('aria-label')||'').match(/\\d+/);"
            "      if (m) n += parseInt(m[0], 10);"
            "      const row = b.closest('[role=\"listitem\"]');"
            "      if (row && !last) {"
            "        const t = row.querySelector('span[dir=\"auto\"][title]');"
            "        if (t) last = t.getAttribute('title')||'';"
            "      }"
            "    });"
            "    return {count: n, sender: last};"
            "  } catch(e) { return {count: 0, sender: '', err: String(e)}; }"
            "})()"
        ),
    },
    "instagram": {
        "url": "https://www.instagram.com/direct/inbox/",
        "title": "Instagram",
        "color": "#E1306C",
        # Instagram unread thread rows carry the `_ac7v` class or an aria-label
        # containing "unread" / "non letto".  We fall back to a rough count.
        "js_unread": (
            "(() => {"
            "  try {"
            "    let n = 0; let last = '';"
            "    const rows = document.querySelectorAll('div[role=\"listitem\"], a[role=\"link\"][href*=\"/direct/t/\"]');"
            "    rows.forEach(r => {"
            "      const dot = r.querySelector('div[aria-label*=\"unread\"], [aria-label*=\"non lett\"]');"
            "      if (dot) {"
            "        n += 1;"
            "        if (!last) {"
            "          const nm = r.querySelector('span[dir=\"auto\"]');"
            "          if (nm) last = nm.innerText.trim();"
            "        }"
            "      }"
            "    });"
            "    return {count: n, sender: last};"
            "  } catch(e) { return {count: 0, sender: '', err: String(e)}; }"
            "})()"
        ),
    },
}


# ----------------------------------------------------------------------
# Reply-confirmation toast — small popup on top of the panel
# ----------------------------------------------------------------------
class _ReplyToast(QWidget):
    reply_yes = pyqtSignal()
    reply_no  = pyqtSignal()

    def __init__(self, sender: str, body: str, color: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.Tool
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedWidth(320)

        card = QWidget(self)
        card.setStyleSheet(f"""
            background: #0b0f12;
            border: 1px solid {color};
            border-radius: 8px;
        """)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        title = QLabel(f"Nuovo messaggio — {sender or '—'}")
        title.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {color}; background: transparent;")
        lay.addWidget(title)

        if body:
            b = QLabel(body[:180])
            b.setWordWrap(True)
            b.setFont(QFont("Courier New", 8))
            b.setStyleSheet("color: #cfe; background: transparent;")
            lay.addWidget(b)

        q = QLabel("Vuoi rispondere?")
        q.setFont(QFont("Courier New", 9))
        q.setStyleSheet("color: #7fd; background: transparent;")
        lay.addWidget(q)

        btns = QHBoxLayout(); btns.setSpacing(6)
        for text, sig, bg in (("Sì", self.reply_yes, color), ("No", self.reply_no, "#333")):
            b = QPushButton(text)
            b.setFixedHeight(26)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: {bg}; color: #001;
                    border: none; border-radius: 4px;
                    font-family: 'Courier New'; font-weight: bold;
                    padding: 0 12px;
                }}
                QPushButton:hover {{ opacity: 0.85; }}
            """)
            b.clicked.connect(sig.emit)
            b.clicked.connect(self.close)
            btns.addWidget(b)
        lay.addLayout(btns)

        outer = QVBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)


# ----------------------------------------------------------------------
# The floating messaging panel itself
# ----------------------------------------------------------------------
class MessagingPanel(QWidget):
    """One floating tendina per platform (whatsapp/instagram)."""

    new_message = pyqtSignal(str, str, str)  # platform, sender, body

    def __init__(self, platform: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.WindowType.Window
                         | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self._platform = platform
        cfg = _PLATFORMS[platform]
        self._color = cfg["color"]
        self._js = cfg["js_unread"]
        self._last_unread = 0
        self._last_sender = ""
        self.setWindowTitle(f"JARVIS — {cfg['title']}")
        self.resize(430, 620)
        self.setStyleSheet(f"background: #05070a; border: 1px solid {self._color};")

        # ---- header bar ----
        hdr = QWidget(self); hdr.setFixedHeight(34)
        hdr.setStyleSheet(f"background: #0a1014; border-bottom: 1px solid {self._color};")
        hlay = QHBoxLayout(hdr); hlay.setContentsMargins(10, 0, 6, 0); hlay.setSpacing(8)

        title_lbl = QLabel(f"◈  {cfg['title'].upper()}")
        title_lbl.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {self._color}; background: transparent; border: none;")
        hlay.addWidget(title_lbl)

        self._badge = QLabel("0")
        self._badge.setFixedHeight(20)
        self._badge.setStyleSheet(f"""
            color: #001; background: {self._color};
            border-radius: 10px; padding: 0 8px;
            font-family: 'Courier New'; font-weight: bold; font-size: 10px;
        """)
        self._badge.hide()
        hlay.addWidget(self._badge)
        hlay.addStretch()

        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet("""
            QPushButton { color: #9df; background: transparent; border: none;
                          font-family: 'Courier New'; font-weight: bold; font-size: 16px; }
            QPushButton:hover { color: #fff; }
        """)
        close_btn.clicked.connect(self.hide)
        hlay.addWidget(close_btn)

        # dragging state
        self._drag_pos: Optional[QPoint] = None

        # ---- web view / fallback ----
        if _WEB_OK:
            self._web = QWebEngineView(self)
            self._web.load(QUrl(cfg["url"]))
        else:
            self._web = QLabel(
                "PyQt6-WebEngine non installato.\n"
                "Esegui: pip install PyQt6-WebEngine",
                self,
            )
            self._web.setStyleSheet("color: #f88; padding: 20px;")
            self._web.setAlignment(Qt.AlignmentFlag.AlignCenter)

        grip = QSizeGrip(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        root.addWidget(hdr)
        root.addWidget(self._web, stretch=1)
        row = QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0); row.addStretch(); row.addWidget(grip)
        root.addLayout(row)

        # ---- poller ----
        self._poll_tmr = QTimer(self)
        self._poll_tmr.timeout.connect(self._poll_unread)
        self._poll_tmr.start(4000)

    # ---- drag from header ----
    def mousePressEvent(self, ev):  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton and ev.position().y() < 34:
            self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
            ev.accept()

    def mouseMoveEvent(self, ev):  # noqa: N802
        if self._drag_pos is not None:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)
            ev.accept()

    def mouseReleaseEvent(self, ev):  # noqa: N802
        self._drag_pos = None
        ev.accept()

    # ---- unread poll ----
    def _poll_unread(self) -> None:
        if not _WEB_OK:
            return
        try:
            self._web.page().runJavaScript(self._js, self._on_unread_result)
        except Exception:
            pass

    def _on_unread_result(self, r) -> None:
        if not isinstance(r, dict):
            return
        n = int(r.get("count", 0) or 0)
        sender = (r.get("sender") or "").strip()
        if n > 0:
            self._badge.setText(str(n))
            self._badge.show()
        else:
            self._badge.hide()
        if n > self._last_unread and sender:
            # ↑ new unread appeared → emit signal (managed by manager)
            self.new_message.emit(self._platform, sender, "")
        self._last_unread = n
        self._last_sender = sender

    # ---- helpers ----
    def announce_unread(self, speak: Optional[Callable[[str], None]] = None) -> str:
        """Return a spoken-friendly sentence describing current unread state."""
        n = self._last_unread
        plat = _PLATFORMS[self._platform]["title"]
        if n <= 0:
            msg = f"Nessun messaggio non letto su {plat}, signore."
        elif n == 1:
            who = f" da {self._last_sender}" if self._last_sender else ""
            msg = f"Signore, hai un messaggio non letto su {plat}{who}."
        else:
            msg = f"Signore, hai {n} messaggi non letti su {plat}."
        if speak:
            try:
                speak(msg)
            except Exception:
                pass
        return msg


# ----------------------------------------------------------------------
# Singleton manager
# ----------------------------------------------------------------------
class _Manager:
    def __init__(self) -> None:
        self._panels: dict[str, MessagingPanel] = {}
        self._toasts: list[_ReplyToast] = []
        self._speak: Optional[Callable[[str], None]] = None
        self._reply_cb: Optional[Callable[[str, str], None]] = None  # (platform, sender)

    def configure(self, speak=None, reply_cb=None) -> None:
        if speak is not None:
            self._speak = speak
        if reply_cb is not None:
            self._reply_cb = reply_cb

    def open(self, platform: str) -> str:
        platform = platform.lower().strip()
        if platform not in _PLATFORMS:
            return f"Piattaforma non supportata: {platform}"
        if QApplication.instance() is None:
            return "GUI non ancora avviata."
        panel = self._panels.get(platform)
        if panel is None:
            panel = MessagingPanel(platform)
            panel.new_message.connect(self._on_new)
            self._panels[platform] = panel
            # position: right of primary screen
            scr = QApplication.primaryScreen().availableGeometry()
            panel.move(scr.right() - panel.width() - 40,
                       scr.top() + 60)
        panel.show(); panel.raise_(); panel.activateWindow()

        # announce unread after webview has (probably) loaded
        QTimer.singleShot(6500, lambda: panel.announce_unread(self._speak))
        return f"Tendina {platform} aperta."

    def close(self, platform: str) -> None:
        p = self._panels.get(platform)
        if p is not None:
            p.hide()

    def notify_external(self, platform: str, sender: str, body: str = "") -> None:
        """Called by check_messages when a new message arrives via poller."""
        self._on_new(platform, sender, body)

    def _on_new(self, platform: str, sender: str, body: str = "") -> None:
        if platform not in _PLATFORMS:
            return
        color = _PLATFORMS[platform]["color"]
        toast = _ReplyToast(sender or "?", body or "", color)
        # position at bottom-right
        scr = QApplication.primaryScreen().availableGeometry()
        toast.adjustSize()
        toast.move(scr.right() - toast.width() - 30,
                   scr.bottom() - toast.height() - 60)

        def _yes():
            if self._speak:
                try:
                    self._speak(f"Va bene signore, cosa vuoi rispondere a {sender}?")
                except Exception:
                    pass
            if self._reply_cb:
                try:
                    self._reply_cb(platform, sender)
                except Exception:
                    pass

        toast.reply_yes.connect(_yes)
        toast.show()
        self._toasts.append(toast)
        # auto-dismiss after 20 s
        QTimer.singleShot(20000, toast.close)


_MANAGER = _Manager()


def get_manager() -> "_Manager":
    return _MANAGER


# ---------- Threading helpers ----------
def open_messaging_panel(platform: str) -> str:
    """Thread-safe: schedule the panel opening on the Qt main thread."""
    from PyQt6.QtCore import QTimer as _QT  # local import safe
    result: dict = {}
    done = threading.Event()

    def _do():
        try:
            result["v"] = _MANAGER.open(platform)
        finally:
            done.set()

    _QT.singleShot(0, _do)
    done.wait(timeout=3.0)
    return result.get("v", f"Tendina {platform} in apertura.")

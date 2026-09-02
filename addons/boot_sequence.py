"""addons/boot_sequence.py — boot animation stile Iron Man (ADDITIVO).

Overlay a tutta finestra mostrato all'avvio di JARVIS: righe di
diagnostica con typewriter + barra di progresso, poi "ACCESS GRANTED"
e dissolve. Click ovunque o ESC per saltare. Nessuna logica esistente
modificata: MainWindow lo istanzia e basta.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget,
)

_BOOT_LINES = [
    ("STARK INDUSTRIES — UNIFIED OS v42.7", 4),
    ("Kernel init ........................", 12),
    ("Neural core [████████████] ......... OK", 26),
    ("Audio matrix calibration .......... OK", 38),
    ("Vision subsystems ................. OK", 51),
    ("Memory lattice [long-term] ........ OK", 63),
    ("Tool matrix: 63 addons ............. OK", 74),
    ("Network uplink — encrypted ........ OK", 85),
    ("Voice interface [Charon] .......... OK", 93),
    ("Weapons safety .................... ENGAGED", 97),
    ("", 97),
    ("Welcome back, sir.", 100),
]


class BootOverlay(QWidget):
    def __init__(self, parent, on_done=None):
        super().__init__(parent)
        from ui import C  # lazy: no import circolare
        self._C = C
        self._on_done = on_done
        self._step_i = 0

        self.setStyleSheet(f"background: {C.BG};")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(60, 50, 60, 40)
        lay.setSpacing(8)

        top = QHBoxLayout()
        logo = QLabel("⬡")
        logo.setFont(QFont("Courier New", 26, QFont.Weight.Bold))
        logo.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        top.addWidget(logo)
        ttl = QLabel("J · A · R · V · I · S   B O O T   S E Q U E N C E")
        ttl.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        ttl.setStyleSheet(f"color: {C.WHITE}; background: transparent;")
        top.addWidget(ttl)
        top.addStretch(1)
        skip = QLabel("[ click / ESC = skip ]")
        skip.setFont(QFont("Courier New", 7))
        skip.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
        top.addWidget(skip)
        lay.addLayout(top)

        self._log = QLabel("")
        self._log.setFont(QFont("Courier New", 10))
        self._log.setStyleSheet(
            f"color: {C.PRI}; background: {C.PANEL};"
            f"border: 1px solid {C.BORDER}; border-radius: 6px; padding: 18px;")
        self._log.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._log.setWordWrap(True)
        lay.addWidget(self._log, stretch=1)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(True)
        self._bar.setFormat("SYSTEMS ONLINE — %p%")
        self._bar.setFixedHeight(18)
        self._bar.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        self._bar.setStyleSheet(f"""
            QProgressBar {{
                background: {C.BAR_BG};
                border: 1px solid {C.BORDER_B};
                border-radius: 3px;
                color: {C.TEXT};
                text-align: center;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {C.PRI_DIM}, stop:0.7 {C.PRI}, stop:1 {C.NEON});
            }}
        """)
        lay.addWidget(self._bar)

        self._final = QLabel("")
        self._final.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._final.setFont(QFont("Courier New", 16, QFont.Weight.Bold))
        self._final.setStyleSheet(f"color: {C.GREEN}; background: transparent;")
        lay.addWidget(self._final)

        self._lines: list[str] = []
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._next)

    def start(self):
        self._tmr.start(320)

    def showEvent(self, e):
        super().showEvent(e)
        par = self.parent()
        if par is not None:
            self.setGeometry(0, 0, par.width(), par.height())

    def _next(self):
        if self._step_i >= len(_BOOT_LINES):
            self._tmr.stop()
            self._final.setText("◈ ACCESS GRANTED ◈")
            QTimer.singleShot(900, self._finish)
            return
        line, pct = _BOOT_LINES[self._step_i]
        self._step_i += 1
        if line:
            self._lines.append(line)
        self._log.setText("\n".join(self._lines))
        self._bar.setValue(pct)

    def _finish(self):
        self.hide()
        self.deleteLater()
        if callable(self._on_done):
            try:
                self._on_done()
            except Exception:
                pass

    def mousePressEvent(self, _e):
        self._tmr.stop()
        self._finish()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._tmr.stop()
            self._finish()

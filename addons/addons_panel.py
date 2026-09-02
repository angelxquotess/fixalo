"""addons/addons_panel.py — browser grafico di tutti gli addon JARVIS.

Overlay nella finestra principale: elenco di tutte le funzioni del
registro con descrizione e tasto ESEGUI (abilitato per gli addon che
non richiedono parametri; gli altri si lanciano a voce o dal campo
comandi).
"""
from __future__ import annotations

import inspect
import threading

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from . import REGISTRY


def _c():
    from ui import C  # lazy: evita import circolare
    return C


def _no_params(fn) -> bool:
    try:
        return all(
            p.default is not inspect.Parameter.empty
            or p.kind in (inspect.Parameter.VAR_POSITIONAL,
                          inspect.Parameter.VAR_KEYWORD)
            for p in inspect.signature(fn).parameters.values()
        )
    except Exception:
        return False


class AddonsOverlay(QWidget):
    def __init__(self, log_sig=None, parent=None):
        super().__init__(parent)
        C = _c()
        self._log_sig = log_sig
        self.setStyleSheet(
            f"background: {C.DARK}; border: 1px solid {C.NEON};"
            f"border-radius: 6px;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        head = QHBoxLayout()
        title = QLabel(f"◈ ADDONS  ·  {len(REGISTRY)} FUNZIONI")
        title.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.NEON}; background: transparent; border: none;")
        head.addWidget(title)
        head.addStretch(1)
        btn_close = QPushButton("CLOSE")
        btn_close.setFont(QFont("Courier New", 7))
        btn_close.clicked.connect(self.hide)
        head.addWidget(btn_close)
        lay.addLayout(head)

        self._filter = QLineEdit()
        self._filter.setPlaceholderText("filtra addon…")
        self._filter.setFont(QFont("Courier New", 8))
        self._filter.setStyleSheet(
            f"background: {C.PANEL2}; color: {C.TEXT};"
            f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px;")
        self._filter.textChanged.connect(self.refresh)
        lay.addWidget(self._filter)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("border: none; background: transparent;")
        self._host = QWidget()
        self._lay = QVBoxLayout(self._host)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(3)
        self._scroll.setWidget(self._host)
        lay.addWidget(self._scroll, stretch=1)

        self.refresh()

    def refresh(self):
        C = _c()
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        q = self._filter.text().lower().strip() if hasattr(self, "_filter") else ""
        for name in sorted(REGISTRY):
            desc, fn = REGISTRY[name]
            if q and q not in name.lower() and q not in desc.lower():
                continue
            self._lay.addWidget(self._row(name, desc, fn))
        self._lay.addStretch(1)

    def _row(self, name: str, desc: str, fn) -> QWidget:
        C = _c()
        row = QWidget()
        row.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 3px;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(8, 4, 8, 4)

        txt = QLabel(f"<b style='color:{C.PRI}'>{name}</b><br>"
                     f"<span style='color:{C.TEXT_MED}'>{desc}</span>")
        txt.setFont(QFont("Courier New", 8))
        txt.setStyleSheet("background: transparent; border: none;")
        rl.addWidget(txt, stretch=1)

        runnable = _no_params(fn)
        btn = QPushButton("ESEGUI" if runnable else "A VOCE")
        btn.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        btn.setEnabled(runnable)
        btn.setCursor(Qt.CursorShape.PointingHandCursor if runnable
                      else Qt.CursorShape.ArrowCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI};"
            f" border: 1px solid {C.PRI_DIM}; border-radius: 3px; padding: 3px 8px; }}"
            f"QPushButton:disabled {{ color: {C.TEXT_DIM}; border-color: {C.BORDER}; }}"
            f"QPushButton:hover {{ background: {C.PRI}; color: {C.DARK}; }}")
        if runnable:
            btn.clicked.connect(lambda _=False, n=name: self._run(n))
        rl.addWidget(btn)
        return row

    def _run(self, name: str):
        def _work():
            from . import run
            res = run(name)
            if self._log_sig is not None:
                try:
                    self._log_sig.emit(f"SYS: [{name}] {str(res)[:300]}")
                except Exception:
                    pass
        threading.Thread(target=_work, daemon=True).start()

"""addons/macro_panel.py — pannello grafico delle scorciatoie vocali.

Widget PyQt6 mostrato dentro la finestra JARVIS (stesso stile HUD):
elenco delle macro con tasto MODIFICA (dialog con JSON degli step),
ELIMINA, creazione nuova macro e aggiornamento lista.
Tutto ADDITIVO: nessuna logica esistente modificata.
"""
from __future__ import annotations

import json

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from .voice_macros import macro_create, macro_delete, macro_list


def _c():
    from ui import C  # import lazy: evita import circolare
    return C


class _EditDialog(QDialog):
    def __init__(self, trigger: str, steps: list, parent=None):
        super().__init__(parent)
        C = _c()
        self.setWindowTitle(f"Modifica: {trigger}")
        self.setMinimumSize(480, 340)
        self.setStyleSheet(f"background: {C.DARK}; color: {C.TEXT};")
        lay = QVBoxLayout(self)

        lbl = QLabel(f"TRIGGER: {trigger}")
        lbl.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(lbl)

        hint = QLabel('Steps JSON: [{"addon": nome, "params": {...}}, ...]')
        hint.setFont(QFont("Courier New", 7))
        hint.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
        lay.addWidget(hint)

        self.editor = QPlainTextEdit()
        self.editor.setFont(QFont("Courier New", 9))
        self.editor.setStyleSheet(
            f"background: {C.PANEL2}; color: {C.TEXT};"
            f"border: 1px solid {C.BORDER}; border-radius: 4px;")
        self.editor.setPlainText(json.dumps(steps, ensure_ascii=False, indent=2))
        lay.addWidget(self.editor, stretch=1)

        self.result_steps: list | None = None
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("ANNULLA")
        cancel.clicked.connect(self.reject)
        save = QPushButton("SALVA")
        save.setStyleSheet(f"background: {C.PRI}; color: #001820; font-weight: bold;")
        save.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        lay.addLayout(btns)

    def _save(self):
        try:
            steps = json.loads(self.editor.toPlainText())
            if not isinstance(steps, list) or not steps:
                raise ValueError("deve essere una lista non vuota")
            self.result_steps = steps
            self.accept()
        except Exception as e:
            self.editor.setPlainText(
                self.editor.toPlainText() +
                f"\n\n// ERRORE JSON: {e}")


class MacroOverlay(QWidget):
    """Overlay scorciatoie vocali dentro la finestra JARVIS."""

    def __init__(self, parent=None):
        super().__init__(parent)
        C = _c()
        self.setStyleSheet(
            f"background: {C.DARK}; border: 1px solid {C.BORDER_B};"
            f"border-radius: 6px;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)

        head = QHBoxLayout()
        title = QLabel("◈ VOICE MACROS")
        title.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {C.PRI}; background: transparent; border: none;")
        head.addWidget(title)
        head.addStretch(1)
        btn_refresh = QPushButton("REFRESH")
        btn_refresh.setFont(QFont("Courier New", 7))
        btn_refresh.clicked.connect(self.refresh)
        head.addWidget(btn_refresh)
        btn_close = QPushButton("CLOSE")
        btn_close.setFont(QFont("Courier New", 7))
        btn_close.clicked.connect(self.hide)
        head.addWidget(btn_close)
        lay.addLayout(head)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet(f"border: none; background: transparent;")
        self._list_host = QWidget()
        self._list_lay = QVBoxLayout(self._list_host)
        self._list_lay.setContentsMargins(0, 0, 0, 0)
        self._list_lay.setSpacing(4)
        self._scroll.setWidget(self._list_host)
        lay.addWidget(self._scroll, stretch=1)

        # --- creazione nuova macro -------------------------------------
        C2 = _c()
        new_lbl = QLabel("▸ NUOVA SCORCIATOIA")
        new_lbl.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        new_lbl.setStyleSheet(f"color: {C2.TEXT_MED}; background: transparent; border: none;")
        lay.addWidget(new_lbl)

        self._new_trigger = QLineEdit()
        self._new_trigger.setPlaceholderText("frase trigger esatta, es. modalita lavoro")
        self._new_trigger.setFont(QFont("Courier New", 8))
        self._new_trigger.setStyleSheet(
            f"background: {C2.PANEL2}; color: {C2.TEXT};"
            f"border: 1px solid {C2.BORDER}; border-radius: 3px; padding: 4px;")
        lay.addWidget(self._new_trigger)

        self._new_steps = QLineEdit()
        self._new_steps.setPlaceholderText(
            '[{"addon":"pomodoro_start","params":{}},{"addon":"eye_rest_start","params":{}}]')
        self._new_steps.setFont(QFont("Courier New", 8))
        self._new_steps.setStyleSheet(self._new_trigger.styleSheet())
        lay.addWidget(self._new_steps)

        btn_add = QPushButton("+ AGGIUNGI SCORCIATOIA")
        btn_add.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        btn_add.setStyleSheet(
            f"background: {C2.PRI}; color: #001820; border-radius: 3px; padding: 5px;")
        btn_add.clicked.connect(self._add)
        lay.addWidget(btn_add)

        self.refresh()

    # ------------------------------------------------------------------
    def refresh(self):
        C = _c()
        while self._list_lay.count():
            item = self._list_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        macros = macro_list()
        if isinstance(macros, str):
            empty = QLabel(macros)
            empty.setFont(QFont("Courier New", 8))
            empty.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent; border: none;")
            self._list_lay.addWidget(empty)
        else:
            for m in macros:
                self._list_lay.addWidget(self._row(m["trigger"], m["steps"]))
        self._list_lay.addStretch(1)

    def _row(self, trigger: str, step_names: list) -> QWidget:
        C = _c()
        row = QWidget()
        row.setStyleSheet(
            f"background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 4px;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(8, 5, 8, 5)

        txt = QLabel(f"⚡ {trigger}\n{' → '.join(step_names)}")
        txt.setFont(QFont("Courier New", 8))
        txt.setStyleSheet(f"color: {C.TEXT}; background: transparent; border: none;")
        rl.addWidget(txt, stretch=1)

        btn_edit = QPushButton("MODIFICA")
        btn_edit.setFont(QFont("Courier New", 7))
        btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_edit.clicked.connect(lambda _=False, t=trigger: self._edit(t))
        rl.addWidget(btn_edit)

        btn_del = QPushButton("✕")
        btn_del.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        btn_del.setStyleSheet(f"color: {C.RED}; background: transparent;")
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.clicked.connect(lambda _=False, t=trigger: self._delete(t))
        rl.addWidget(btn_del)
        return row

    # ------------------------------------------------------------------
    def _edit(self, trigger: str):
        from .core import load_store
        macros = load_store("macros", {})
        steps = macros.get(trigger, [])
        dlg = _EditDialog(trigger, steps, self)
        if dlg.exec() and dlg.result_steps:
            macro_create(trigger, json.dumps(dlg.result_steps, ensure_ascii=False))
            self.refresh()

    def _delete(self, trigger: str):
        macro_delete(trigger)
        self.refresh()

    def _add(self):
        trigger = self._new_trigger.text().strip()
        steps = self._new_steps.text().strip()
        if not trigger or not steps:
            return
        msg = macro_create(trigger, steps)
        if "creata" in msg:
            self._new_trigger.clear()
            self._new_steps.clear()
        self.refresh()

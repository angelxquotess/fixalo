"""
jarvis_perf.py — Patch di performance ADDITIVA per JARVIS.

Non modifica nessun file esistente: viene importata dal nuovo launcher
`start_jarvis_boosted.py` PRIMA di main e applica monkey-patch sicuri:

1. Cache di _get_api_key / _load_system_prompt (evita I/O su disco ad
   ogni controllo memoria e ad ogni riconnessione).
2. FPS adattivi della HUD: l'animazione si ferma quando la finestra e'
   minimizzata o nascosta, riparte quando torna visibile.
3. Interval minimo globale dei QTimer (niente timer sotto i 15ms).
4. Tuning del garbage collector (meno pause, soglie piu' alte).
5. Flag Qt/WebEngine per ridurre il carico GPU/CPU del Chromium embedded.
6. Priorita' del processo abbassata (ridondante ma sicura).

Uso:
    import jarvis_perf
    jarvis_perf.apply()
"""
from __future__ import annotations

import functools
import gc
import os
import sys

_APPLIED = False


def _set_process_priority() -> None:
    try:
        import psutil
        p = psutil.Process()
        if sys.platform.startswith("win"):
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        else:
            p.nice(5)
    except Exception:
        pass


def _tune_gc() -> None:
    try:
        gc.set_threshold(50000, 500, 1000)
        gc.freeze()
    except Exception:
        pass


def _qt_flags() -> None:
    # Riduce il costo del Chromium embedded (WhatsApp overlay).
    os.environ.setdefault(
        "QTWEBENGINE_CHROMIUM_FLAGS",
        "--disable-gpu-compositing --disable-background-timer-throttling=0 "
        "--disable-renderer-backgrounding --disable-features=TranslateUI "
        "--mute-audio --force-dark-mode"
    )
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "0")


def _patch_main_caches() -> None:
    """Cache di API key e system prompt: il file veniva riletto da disco
    ad ogni chiamata (controlli memoria, riconnessioni live)."""
    try:
        import main as _main
        _main._get_api_key = functools.lru_cache(maxsize=1)(_main._get_api_key)
        _main._load_system_prompt = functools.lru_cache(maxsize=1)(
            _main._load_system_prompt
        )
    except Exception:
        pass
    try:
        import or_client as _orc
        _orc._load_api_key = functools.lru_cache(maxsize=1)(_orc._load_api_key)
    except Exception:
        pass


def _patch_qtimer_minimum() -> None:
    """Nessun QTimer puo' girare sotto i 15ms: timer troppo fitti sono la
    causa classica di CPU al 100% nelle app Qt."""
    try:
        from PyQt6.QtCore import QTimer
        _orig_start = QTimer.start

        def _safe_start(self, msec=None):
            if msec is not None and isinstance(msec, int) and 0 < msec < 15:
                msec = 15
            if msec is None:
                return _orig_start(self)
            return _orig_start(self, msec)

        QTimer.start = _safe_start
    except Exception:
        pass


def _patch_adaptive_hud() -> None:
    """Ferma l'animazione della HUD quando la finestra non e' visibile:
    repaint a 30fps di una finestra nascosta = CPU sprecata."""
    try:
        import ui as _ui

        _orig_step = _ui.HudCanvas._step

        def _adaptive_step(self):
            try:
                w = self.window()
                if w is not None and (w.isMinimized() or not w.isVisible()):
                    return  # salta il repaint: la finestra non si vede
            except Exception:
                pass
            return _orig_step(self)

        _ui.HudCanvas._step = _adaptive_step
    except Exception:
        pass

    try:
        import ui as _ui
        _orig_animate = _ui.FileDropZone._animate

        def _adaptive_animate(self):
            try:
                w = self.window()
                if w is not None and (w.isMinimized() or not w.isVisible()):
                    return
            except Exception:
                pass
            return _orig_animate(self)

        _ui.FileDropZone._animate = _adaptive_animate
    except Exception:
        pass


def apply() -> None:
    global _APPLIED
    if _APPLIED:
        return
    _APPLIED = True
    _qt_flags()          # PRIMA di importare PyQt6/QtWebEngine
    _tune_gc()
    _set_process_priority()
    _patch_qtimer_minimum()
    _patch_main_caches()
    _patch_adaptive_hud()
    print("[jarvis_perf] ✅ Patch di performance applicate.")


if __name__ == "__main__":
    apply()

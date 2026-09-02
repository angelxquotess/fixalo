"""
Global hotkey manager. Uses the `keyboard` library on Windows/Linux.
Falls back to a no-op when the package (or root privileges on Linux)
is not available.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional


class GlobalHotkey:
    def __init__(self, sequence: str, on_press: Callable[[], None]) -> None:
        self._seq = sequence
        self._cb  = on_press
        self._thread: Optional[threading.Thread] = None
        self._handle = None
        self._available = False
        try:
            import keyboard  # noqa: F401
            self._available = True
        except Exception as e:
            print(f"[Hotkey] `keyboard` package unavailable: {e}")

    @property
    def available(self) -> bool:
        return self._available

    def start(self) -> None:
        if not self._available or self._thread is not None:
            return

        def _run():
            try:
                import keyboard
                self._handle = keyboard.add_hotkey(
                    self._seq,
                    lambda: self._safe_call(),
                    suppress=False,
                )
                keyboard.wait()  # blocks; released when process exits
            except Exception as e:
                print(f"[Hotkey] loop error: {e}")

        self._thread = threading.Thread(
            target=_run, daemon=True, name="global-hotkey"
        )
        self._thread.start()

    def _safe_call(self):
        try:
            self._cb()
        except Exception as e:
            print(f"[Hotkey] callback error: {e}")

    def stop(self) -> None:
        try:
            import keyboard
            if self._handle is not None:
                keyboard.remove_hotkey(self._handle)
                self._handle = None
        except Exception:
            pass

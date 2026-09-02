"""
tray_manager.py
================

Fase 4 — Minimize to tray

Provides:
    * FloatingArcReactor       — a small (80×80) frameless, always-on-top
                                 draggable Qt widget that displays a stylised
                                 arc reactor "J" icon.  It re-opens the main
                                 HUD on left-click.
    * TrayManager              — a `pystray` background icon (Windows/Linux)
                                 with left-click toggle mute and right-click
                                 menu: "Mostra" / "Esci".

Both objects are owned by ``MainWindow``.  When the user issues the voice
command "minimizzati" / "nasconditi", or presses the "–" HUD button, the
main window is hidden, the waveform repaint is paused, the camera preview
is throttled to 1 fps and this floating icon + tray icon are shown.

On "mostrati" / "torna" (voice) or via the floating icon / tray menu the
main window is restored and every animation resumes.

Left-click on the tray icon restores the main HUD window (open only).
Right-click toggles microphone mute: icon turns red while muted,
back to cyan on unmute. This mirrors the F4 / on-screen mute button.

The module keeps every heavy import lazy so it costs almost nothing when
the tray is never opened.
"""

from __future__ import annotations

import math
import threading
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QPointF
from PyQt6.QtGui import (
    QBrush, QColor, QConicalGradient, QPainter, QPen, QRadialGradient,
)
from PyQt6.QtWidgets import QWidget


# ----------------------------------------------------------------------
# Floating draggable arc-reactor icon
# ----------------------------------------------------------------------
class FloatingArcReactor(QWidget):
    """Small always-on-top draggable icon shown when the HUD is minimized.

    Left-click restores the main HUD window. Right-click toggles
    microphone mute: the icon turns red while muted, back to cyan on
    unmute — mirrors the tray icon / F4 mute button.
    """

    #: emitted with no args → user requested the main window back
    restore_requested = pyqtSignal()

    #: emitted with the new mute state whenever right-click toggles it
    mute_toggled = pyqtSignal(bool)

    _SIZE = 84  # px

    # Colors (RGBA) — kept in sync with TrayManager's palette
    _COLOR_ACTIVE_RING = QColor(140, 250, 255, 200)
    _COLOR_ACTIVE_CORE_HI = QColor(255, 255, 255, 255)
    _COLOR_ACTIVE_CORE_LO = QColor(120, 250, 255, 230)
    _COLOR_ACTIVE_SPOKE = QColor(120, 240, 255, 180)
    _COLOR_ACTIVE_CONIC_HI = QColor(0, 220, 255, 220)
    _COLOR_ACTIVE_CONIC_LO = QColor(0, 90, 130, 40)
    _COLOR_ACTIVE_GLOW_HI = QColor(80, 240, 255, 90)
    _COLOR_ACTIVE_GLOW_LO = QColor(20, 60, 80, 40)

    _COLOR_MUTED_RING = QColor(255, 90, 110, 200)
    _COLOR_MUTED_CORE_HI = QColor(255, 255, 255, 255)
    _COLOR_MUTED_CORE_LO = QColor(255, 120, 130, 230)
    _COLOR_MUTED_SPOKE = QColor(240, 90, 110, 180)
    _COLOR_MUTED_CONIC_HI = QColor(255, 60, 80, 220)
    _COLOR_MUTED_CONIC_LO = QColor(130, 20, 30, 40)
    _COLOR_MUTED_GLOW_HI = QColor(255, 80, 90, 90)
    _COLOR_MUTED_GLOW_LO = QColor(80, 20, 25, 40)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        on_mute_toggle: Optional[Callable[[], Optional[bool]]] = None,
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(self._SIZE, self._SIZE)
        self.setToolTip("JARVIS — click to restore")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Callback that performs the REAL microphone mute in the host
        # app and returns the resulting state (True = now muted). If
        # None, the icon still toggles its own visual state, but no
        # actual muting happens — pass this in to wire it up for real.
        self._on_mute_toggle = on_mute_toggle
        self._muted = False

        # animation
        self._angle = 0.0
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._tick)
        self._tmr.start(40)

        # drag state
        self._drag_offset: Optional[QPointF] = None
        self._pressed_pos: Optional[QPointF] = None
        self._is_dragging = False
        self._right_pressed = False

    # ------- animation -------
    def _tick(self) -> None:
        self._angle = (self._angle + 3.0) % 360.0
        self.update()

    # ------- painting -------
    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = self.width()
        cx = w / 2.0

        # pick the active/muted palette
        if self._muted:
            c_ring = self._COLOR_MUTED_RING
            c_core_hi, c_core_lo = self._COLOR_MUTED_CORE_HI, self._COLOR_MUTED_CORE_LO
            c_spoke = self._COLOR_MUTED_SPOKE
            c_conic_hi, c_conic_lo = self._COLOR_MUTED_CONIC_HI, self._COLOR_MUTED_CONIC_LO
            c_glow_hi, c_glow_lo = self._COLOR_MUTED_GLOW_HI, self._COLOR_MUTED_GLOW_LO
        else:
            c_ring = self._COLOR_ACTIVE_RING
            c_core_hi, c_core_lo = self._COLOR_ACTIVE_CORE_HI, self._COLOR_ACTIVE_CORE_LO
            c_spoke = self._COLOR_ACTIVE_SPOKE
            c_conic_hi, c_conic_lo = self._COLOR_ACTIVE_CONIC_HI, self._COLOR_ACTIVE_CONIC_LO
            c_glow_hi, c_glow_lo = self._COLOR_ACTIVE_GLOW_HI, self._COLOR_ACTIVE_GLOW_LO

        # backdrop soft glow
        glow = QRadialGradient(cx, cx, cx)
        glow.setColorAt(0.0, c_glow_hi)
        glow.setColorAt(0.55, c_glow_lo)
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(1, 1, w - 2, w - 2)

        # outer ring
        p.setPen(QPen(c_ring, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(6, 6, w - 12, w - 12)

        # rotating conic gradient ring (mimics arc-reactor energy loop)
        conic = QConicalGradient(cx, cx, self._angle)
        conic.setColorAt(0.00, c_conic_hi)
        conic.setColorAt(0.35, c_conic_lo)
        conic.setColorAt(0.65, c_conic_hi)
        conic.setColorAt(1.00, c_conic_lo)
        p.setPen(QPen(QBrush(conic), 3))
        p.drawEllipse(12, 12, w - 24, w - 24)

        # 8-way spokes
        p.save()
        p.translate(cx, cx)
        p.setPen(QPen(c_spoke, 1.5))
        r_inner, r_outer = w * 0.18, w * 0.36
        for i in range(8):
            a = math.radians(i * 45 + self._angle * 0.5)
            x1 = math.cos(a) * r_inner
            y1 = math.sin(a) * r_inner
            x2 = math.cos(a) * r_outer
            y2 = math.sin(a) * r_outer
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        p.restore()

        # inner core
        core = QRadialGradient(cx, cx, w * 0.22)
        core.setColorAt(0.0, c_core_hi)
        core.setColorAt(0.45, c_core_lo)
        core.setColorAt(1.0, QColor(0, 90, 130, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(core))
        p.drawEllipse(int(cx - w * 0.22), int(cx - w * 0.22),
                      int(w * 0.44), int(w * 0.44))

    # ------- drag + click -------
    def mousePressEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton:
            self._pressed_pos = ev.globalPosition()
            self._drag_offset = ev.globalPosition() - QPointF(
                self.frameGeometry().topLeft()
            )
            self._is_dragging = False
            ev.accept()
        elif ev.button() == Qt.MouseButton.RightButton:
            # right-click never drags — just arms the mute toggle
            self._right_pressed = True
            ev.accept()

    def mouseMoveEvent(self, ev) -> None:  # noqa: N802
        if self._drag_offset is None:
            return
        if not self._is_dragging and self._pressed_pos is not None:
            if (ev.globalPosition() - self._pressed_pos).manhattanLength() > 6:
                self._is_dragging = True
        if self._is_dragging:
            new_top_left = ev.globalPosition() - self._drag_offset
            self.move(int(new_top_left.x()), int(new_top_left.y()))
            ev.accept()

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        was_left_click = (
            ev.button() == Qt.MouseButton.LeftButton
            and not self._is_dragging
        )
        was_right_click = (
            ev.button() == Qt.MouseButton.RightButton
            and self._right_pressed
        )
        self._drag_offset = None
        self._pressed_pos = None
        self._is_dragging = False
        self._right_pressed = False
        if was_left_click:
            self.restore_requested.emit()
        elif was_right_click:
            self._toggle_mute()
        ev.accept()

    # ------- mute state -------
    def _toggle_mute(self) -> None:
        new_state = not self._muted
        if self._on_mute_toggle is not None:
            try:
                result = self._on_mute_toggle()
            except Exception as exc:
                print(f"[FloatingArcReactor] mute toggle callback failed: {exc}")
            else:
                if result is not None:
                    new_state = bool(result)
        self._muted = new_state
        self.setToolTip(
            "JARVIS — MUTED (right-click to unmute)"
            if self._muted
            else "JARVIS — click to restore"
        )
        self.update()
        self.mute_toggled.emit(self._muted)

    def set_muted(self, muted: bool) -> None:
        """External API: sync icon state when mute is toggled elsewhere
        (F4 shortcut, on-screen mute button, tray icon, ...)."""
        muted = bool(muted)
        if muted == self._muted:
            return
        self._muted = muted
        self.setToolTip(
            "JARVIS — MUTED (right-click to unmute)"
            if self._muted
            else "JARVIS — click to restore"
        )
        self.update()

    @property
    def muted(self) -> bool:
        return self._muted

    # ------- lifecycle -------
    def start_anim(self) -> None:
        if not self._tmr.isActive():
            self._tmr.start(40)

    def stop_anim(self) -> None:
        if self._tmr.isActive():
            self._tmr.stop()


# ----------------------------------------------------------------------
# System-tray icon (pystray, background thread)
# ----------------------------------------------------------------------
class TrayManager:
    """
    Wrapper around ``pystray`` running its event loop in a background
    thread.  All callbacks are executed inside that thread; the caller
    must therefore marshal Qt actions back to the GUI thread (we use a
    ``QTimer.singleShot(0, ...)`` in ``ui.py``).

    Left-click on the tray icon restores the main HUD window.
    Right-click toggles microphone mute (icon turns red while muted).
    """

    # Colors (RGBA)
    _COLOR_ACTIVE_RING = (140, 250, 255, 255)
    _COLOR_ACTIVE_INNER = (0, 220, 255, 255)
    _COLOR_ACTIVE_CORE = (200, 250, 255, 255)
    _COLOR_ACTIVE_SPOKE = (120, 240, 255, 255)

    _COLOR_MUTED_RING = (255, 90, 110, 255)
    _COLOR_MUTED_INNER = (230, 40, 60, 255)
    _COLOR_MUTED_CORE = (255, 200, 205, 255)
    _COLOR_MUTED_SPOKE = (240, 90, 110, 255)

    def __init__(
        self,
        on_show: Callable[[], None],
        on_exit: Callable[[], None],
        on_mute_toggle: Optional[Callable[[], bool]] = None,
        title: str = "JARVIS",
    ) -> None:
        self._on_show = on_show
        self._on_exit = on_exit
        # Callback that toggles mute in the host app and returns the new
        # muted state (True = now muted). If None, tray still toggles its
        # own visual state without affecting the mic.
        self._on_mute_toggle = on_mute_toggle
        self._title = title
        self._icon = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._muted = False

    # ---- icon image ----
    @classmethod
    def _build_image(cls, size: int = 64, muted: bool = False):
        """Draw a small arc-reactor style PNG in memory (PIL).

        muted=True → red palette to signal the microphone is off.
        """
        from PIL import Image, ImageDraw

        if muted:
            ring = cls._COLOR_MUTED_RING
            inner = cls._COLOR_MUTED_INNER
            core = cls._COLOR_MUTED_CORE
            spoke = cls._COLOR_MUTED_SPOKE
        else:
            ring = cls._COLOR_ACTIVE_RING
            inner = cls._COLOR_ACTIVE_INNER
            core = cls._COLOR_ACTIVE_CORE
            spoke = cls._COLOR_ACTIVE_SPOKE

        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # outer ring
        d.ellipse((2, 2, size - 3, size - 3), outline=ring, width=3)
        # inner ring
        inner_off = size // 5
        d.ellipse(
            (inner_off, inner_off, size - inner_off - 1, size - inner_off - 1),
            outline=inner,
            width=2,
        )
        # core
        core_off = size // 3
        d.ellipse(
            (core_off, core_off, size - core_off - 1, size - core_off - 1),
            fill=core,
        )
        # spokes
        cx = size / 2
        r1, r2 = size * 0.22, size * 0.38
        for i in range(8):
            a = math.radians(i * 45)
            d.line(
                (
                    cx + math.cos(a) * r1,
                    cx + math.sin(a) * r1,
                    cx + math.cos(a) * r2,
                    cx + math.sin(a) * r2,
                ),
                fill=spoke,
                width=2,
            )
        # When muted, overlay a red diagonal slash to reinforce the
        # "microphone off" semantics.
        if muted:
            d.line(
                (int(size * 0.18), int(size * 0.18),
                 int(size * 0.82), int(size * 0.82)),
                fill=(255, 40, 60, 255),
                width=4,
            )
        return img

    # ---- lifecycle ----
    def start(self) -> None:
        if self._running:
            return
        try:
            import pystray
        except Exception as exc:  # pragma: no cover
            print(f"[Tray] pystray not available: {exc}")
            return

        image = self._build_image(muted=self._muted)
        # On Windows, `default=True` marks the item invoked by a single
        # left-click on the tray icon. We wire it to the SHOW action so
        # a single left-click restores the main HUD. Right-click opens
        # the menu but we ALSO hook WM_RBUTTONUP below so a plain
        # right-click toggles mute directly (without needing the menu).
        menu = pystray.Menu(
            pystray.MenuItem(
                "Mostra",
                self._handle_show,
                default=True,
            ),
            pystray.MenuItem(
                self._mute_label,
                self._handle_mute_toggle,
            ),
            pystray.MenuItem("Esci", self._handle_exit),
        )
        self._icon = pystray.Icon("jarvis", image, self._title, menu)

        # ---------- Windows: force single-click semantics ----------
        # pystray installs/initializes its Windows message handlers when
        # Icon.run() starts.  Therefore the hook must be installed from
        # pystray's `setup` callback, not before the run loop starts.
        self._running = True

        def _run_tray() -> None:
            try:
                import platform as _plat

                # pystray calls setup(icon), so the callback must accept
                # the Icon instance. Keep the actual hook method unchanged.
                def _setup(_icon) -> None:
                    if _plat.system() == "Windows":
                        self._install_single_click_hook()

                self._icon.run(setup=_setup)
            except Exception as exc:
                print(f"[Tray] tray loop failed: {exc}")

        self._thread = threading.Thread(
            target=_run_tray, daemon=True, name="tray-icon"
        )
        self._thread.start()

    def _install_single_click_hook(self) -> None:
        """Ensure a *single* left-click restores the HUD and a *single*
        right-click toggles mute.

        We patch pystray's per-icon ``_message_handlers`` dict (used by
        the internal WndProc dispatcher on Windows) AND override the
        icon's bound ``_on_notify`` attribute, so that regardless of
        which dispatch path pystray uses in the installed version, our
        wrapper is picked up.

        Any exception is swallowed so the tray keeps working with the
        built-in behaviour if the internal pystray API changes.
        """
        icon = self._icon
        if icon is None:
            return

        # --- resolve constants ---
        try:
            from pystray._util import win32 as _pw32  # type: ignore
            WM_NOTIFY = getattr(_pw32, "WM_NOTIFY", None)
            WM_LBUTTONUP = getattr(_pw32, "WM_LBUTTONUP", 0x0202)
            WM_LBUTTONDBLCLK = getattr(_pw32, "WM_LBUTTONDBLCLK", 0x0203)
            WM_RBUTTONUP = getattr(_pw32, "WM_RBUTTONUP", 0x0205)
            WM_RBUTTONDBLCLK = getattr(_pw32, "WM_RBUTTONDBLCLK", 0x0206)
        except Exception:
            WM_NOTIFY = None
            WM_LBUTTONUP = 0x0202
            WM_LBUTTONDBLCLK = 0x0203
            WM_RBUTTONUP = 0x0205
            WM_RBUTTONDBLCLK = 0x0206

        handlers = getattr(icon, "_message_handlers", None)

        # Fallback: locate WM_NOTIFY key by inspecting registered handler
        # names (survives minor pystray refactors).
        if WM_NOTIFY is None and isinstance(handlers, dict):
            for k, v in handlers.items():
                if getattr(v, "__name__", "") == "_on_notify":
                    WM_NOTIFY = k
                    break

        original_notify = None
        if isinstance(handlers, dict) and WM_NOTIFY in handlers:
            original_notify = handlers[WM_NOTIFY]
        else:
            original_notify = getattr(icon, "_on_notify", None)

        if original_notify is None:
            print("[Tray] hook: no _on_notify handler found — falling back to menu")
            return

        _left = {WM_LBUTTONUP}
        _right = {WM_RBUTTONUP}

        def _wrapped(wparam, lparam):
            # pystray's Windows backend passes the tray mouse message
            # (WM_LBUTTONUP / WM_RBUTTONUP / ...) as lParam directly.
            # Do not mask it to the low word: on some builds this prevents
            # the event from matching and the right-click silently falls
            # through to pystray's normal context-menu handling.
            try:
                ev = int(lparam)
            except Exception:
                ev = lparam
            try:
                if ev in _left:
                    try:
                        self._handle_show()
                    except Exception as exc:
                        print(f"[Tray] show handler failed: {exc}")
                    return 0
                if ev in _right:
                    try:
                        self._handle_mute_toggle()
                    except Exception as exc:
                        print(f"[Tray] mute toggle failed: {exc}")
                    # Return early so pystray does NOT open its own
                    # context menu on right-click.
                    return 0
            except Exception as exc:
                print(f"[Tray] hook dispatch error: {exc}")
            try:
                return original_notify(wparam, lparam)
            except Exception:
                return 0

        # Install into the message handlers dict (primary path).
        if isinstance(handlers, dict) and WM_NOTIFY is not None:
            try:
                handlers[WM_NOTIFY] = _wrapped
            except Exception as exc:
                print(f"[Tray] handlers dict patch failed: {exc}")

        # Also override the bound method on the instance as a safety
        # net (some pystray forks read ``icon._on_notify`` directly).
        try:
            icon._on_notify = _wrapped  # type: ignore[attr-defined]
        except Exception:
            pass

        print("[Tray] single-click hook installed "
              f"(WM_NOTIFY={WM_NOTIFY}, RBUTTONUP={WM_RBUTTONUP})")

    def stop(self) -> None:
        if not self._running:
            return
        try:
            if self._icon is not None:
                self._icon.stop()
        except Exception:
            pass
        self._running = False
        self._icon = None
        self._thread = None

    # ---- dynamic menu label ----
    def _mute_label(self, _item=None) -> str:
        return "Riattiva microfono" if self._muted else "Silenzia microfono"

    def _refresh_icon(self) -> None:
        """Rebuild the tray image + refresh menu (label + default marker)."""
        if self._icon is None:
            return
        try:
            self._icon.icon = self._build_image(muted=self._muted)
            self._icon.title = (
                f"{self._title} — MUTED" if self._muted else self._title
            )
            # Refresh the dynamic menu label. pystray re-evaluates the
            # menu when `update_menu` is called.
            self._icon.update_menu()
        except Exception:
            pass

    def set_muted(self, muted: bool) -> None:
        """External API: sync tray state when mute is toggled elsewhere
        (F4 shortcut, on-screen mute button, ...)."""
        if bool(muted) == self._muted:
            return
        self._muted = bool(muted)
        self._refresh_icon()

    # ---- menu handlers ----
    def _handle_mute_toggle(self, icon=None, item=None) -> None:  # noqa: ARG002
        # Flip local state first (optimistic UI), then delegate to the
        # host app which may override the final state.
        self._muted = not self._muted
        if self._on_mute_toggle is not None:
            try:
                new_state = self._on_mute_toggle()
                if isinstance(new_state, bool):
                    self._muted = new_state
            except Exception as exc:
                print(f"[Tray] mute toggle callback failed: {exc}")
        self._refresh_icon()

    def _handle_show(self, icon=None, item=None) -> None:  # noqa: ARG002
        try:
            self._on_show()
        finally:
            self.stop()

    def _handle_exit(self, icon=None, item=None) -> None:  # noqa: ARG002
        try:
            self._on_exit()
        finally:
            self.stop()

    @property
    def running(self) -> bool:
        return self._running

    @property
    def muted(self) -> bool:
        return self._muted

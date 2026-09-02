# CHANGELOG — Tray / Floating Icon / Hotkey (Jan 2026)

## What's new in this build

### 1. Floating Jarvis icon (draggable) + companion mute button
When the HUD is minimized (button, voice, or hotkey) the app **no longer
just disappears**: a small always-on-top capsule appears with

- **Reactor icon** (left, ~84 px): drag it to move both widgets, left-click
  to restore the full HUD, right-click for the context menu.
- **Mute button** (right, ~44 px): microphone glyph with a red slash
  when the mic is muted. Click toggles mute/unmute directly, without
  reopening the HUD.

### 2. Haptic feedback on mute/unmute
On every mute toggle (whether from the floating button, the right-click
menu, or the HUD's own button syncing back to the floater) the app fires:

- **System beep** — `QApplication.beep()` cross-platform, plus a
  Windows-only `winsound.MessageBeep()` with a **different tone**
  between mute (`ICONASTERISK`) and unmute (`ICONEXCLAMATION`) so you
  can tell them apart with eyes closed.
- **Visual flash** — a red/cyan halo pulse around the mute button that
  fades over ~0.7 s. Timed to the tone.
- **Tray balloon** — "🔇 Microfono silenziato" / "🎙 Microfono attivo".

### 3. Live coloured status ring
The reactor icon's outer ring changes colour in real time to reflect
the assistant's state — no need to reopen the HUD to know what it is
doing. Even the pulsating halo takes the same colour so the state is
readable at a glance.

| Assistant state | Ring / halo colour       |
| --------------- | ------------------------ |
| `LISTENING`     | green   `#00ff88`        |
| `SPEAKING`      | orange  `#ff6b00`        |
| `THINKING`      | amber   `#ffcc00`        |
| `INITIALISING`  | dim cyan `#5ab8cc`       |
| `SLEEPING`      | slate   `#5a5a78`        |
| `MUTED` (mic)   | red     `#ff3366`        |

Muted always wins over the underlying state, so if you mute mid-reply
the ring flips to red immediately and returns to the live state on
unmute. Backed by `FloatingJarvis.set_state()` — pushed from
`MainWindow._apply_state()` on every state change.

### 2. Fix — voice command "nasconditi" no longer quits the app
Root cause: hiding the last visible window was letting Qt shut down the
process (`quitOnLastWindowClosed=True`, the Qt default). We now flip
that flag off *before* hiding and back on when the HUD is restored.

### 3. Fix — voice command "mostrati" no longer triggers the camera
**v2 fix (definitive)**: earlier we only intercepted the transcript,
but Gemini decides tool calls **before** the transcript reaches us —
so `screen_process(angle='camera')` was already firing.

Now `_execute_tool()` inspects every `screen_process` call: if its
`text` argument matches any minimize/restore keyword we **block the
capture** entirely and route the command through
`_maybe_handle_visibility_cmd()`. The tool returns a clean OK response
so Gemini's turn ends without the 1007 `CONTENT_TYPE_AUDIO`
websocket crash we were seeing when interrupting mid-frame.

Extended keyword list (word-boundary matched):
* **Hide**: `minimizzati`, `nasconditi`, `vai in tray`, `sparisci`, `vai via`
* **Show**: `mostrati`, `riappari`, `torna`, `torna qui`, `ricompari`, `fatti vedere`
Root cause: substring matching + Gemini's tool call for "mostrami/mostra".
Fixes:
- **Word-boundary regex** matching (`\bmostrati\b`), so "mostrami" no
  longer ambiguously fires the restore command.
- On every visibility hit we immediately call `self.interrupt()` to
  drain the audio queue and cancel Gemini's in-flight tool call.

### 4. Global hotkey — Win + Shift + J
Works even when JARVIS is not the focused window. Toggles between the
full HUD and the floating icon. Backed by the cross-platform `keyboard`
package (`hotkey_manager.py`). Silently no-ops when the package is
unavailable.

### 5. Tray balloon notifications
When JARVIS finishes speaking **and** the HUD is minimized, a small
Windows toast/balloon is fired via `pystray.Icon.notify()` with a
120-char excerpt of the reply — so you'll never miss an answer while
working in another window.

## Voice-command reference (final list)

| Utterance                                          | Action              |
| -------------------------------------------------- | ------------------- |
| `minimizzati`, `nasconditi`, `vai in tray`         | Show floating icon  |
| `mostrati`, `riappari`, `torna qui`, `ricompari`   | Restore full HUD    |
| **Win + Shift + J**                                | Toggle (global)     |

## Files touched
- `ui.py` — new `FloatingJarvis` widget; refactored `minimize_to_tray`
  / `restore_from_tray`; hotkey wiring; `notify()` helper.
- `main.py` — `_maybe_handle_visibility_cmd` now uses `\b` word
  boundaries; new keyword set; calls `self.interrupt()` on match; tray
  balloon in `set_speaking(False)` when HUD hidden.
- `tray_manager.py` — added `notify(title, message)`.
- `hotkey_manager.py` — new; wraps `keyboard.add_hotkey`.
- `requirements.txt` — added `keyboard`.

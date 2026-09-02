# actions/message_state.py
# Stato condiviso fra i poller di notifiche e i comandi:
#   - "rispondi con <testo>"
#   - "Jarvis riproduci il vocale" (se l'ultimo era audio)
#   - "Jarvis suggeriscimi una risposta" + "Jarvis rispondi cosi'"
#   - "Jarvis leggimi le ultime N notifiche"
#
# Compatibile API con la versione vecchia:
#   set_last_incoming(platform, sender)        # firma corta, ancora supportata
#   set_last_incoming(platform, sender, body=..., kind=..., audio_url=..., audio_path=...)
#   get_last_incoming()  -> (platform, sender) | None

from __future__ import annotations
import threading
from collections import deque
from typing import Callable, Optional, Any

_lock = threading.Lock()
_last_incoming: Optional[tuple[str, str]] = None   # (platform, sender)
_last_per_platform: dict[str, dict] = {}           # plat -> full dict
_listeners: list[Callable[[str, str], None]] = []

# Buffer per il comando "leggimi le ultime N notifiche"
_INBOX_MAX = 50
_inbox: deque[dict] = deque(maxlen=_INBOX_MAX)     # cronologia notifiche

# Buffer per "suggeriscimi una risposta" / "rispondi cosi'"
_last_ai_suggestions: list[str] = []
_last_ai_picked: Optional[str] = None              # se l'utente ha scelto


def set_last_incoming(platform: str, sender: str,
                      body: str = "",
                      kind: str = "text",
                      audio_url: str = "",
                      audio_path: str = "",
                      msg_id: str = "") -> None:
    """kind: 'text' | 'voice' | 'image' | 'video' | 'sticker' | 'other'"""
    global _last_incoming
    if not platform or not sender:
        return
    rec = {
        "platform":   platform,
        "sender":     sender,
        "body":       body or "",
        "kind":       kind or "text",
        "audio_url":  audio_url or "",
        "audio_path": audio_path or "",
        "msg_id":     msg_id or "",
    }
    with _lock:
        _last_incoming = (platform, sender)
        _last_per_platform[platform] = rec
        _inbox.append(rec)
        listeners = list(_listeners)
    for cb in listeners:
        try:
            cb(platform, sender)
        except Exception:
            pass


def get_last_incoming() -> Optional[tuple[str, str]]:
    with _lock:
        return _last_incoming


def get_last_record() -> Optional[dict]:
    """Ritorna l'ultimo record completo (con body/kind/audio_url)."""
    with _lock:
        if not _last_incoming:
            return None
        plat, _ = _last_incoming
        rec = _last_per_platform.get(plat)
        return dict(rec) if rec else None


def get_last_for_platform(platform: str) -> Optional[str]:
    with _lock:
        rec = _last_per_platform.get(platform)
        return rec.get("sender") if rec else None


def get_last_record_for_platform(platform: str) -> Optional[dict]:
    with _lock:
        rec = _last_per_platform.get(platform)
        return dict(rec) if rec else None


def get_recent_notifications(n: int = 5) -> list[dict]:
    """Ritorna gli ultimi N record cronologici (piu' recenti per ultimi)."""
    n = max(1, min(n, _INBOX_MAX))
    with _lock:
        return list(_inbox)[-n:]


def register_listener(cb: Callable[[str, str], None]) -> None:
    with _lock:
        if cb not in _listeners:
            _listeners.append(cb)


def clear_last_incoming() -> None:
    global _last_incoming
    with _lock:
        _last_incoming = None


# ---- AI reply suggestions ----

def set_ai_suggestions(suggestions: list[str]) -> None:
    global _last_ai_suggestions, _last_ai_picked
    with _lock:
        _last_ai_suggestions = [s for s in (suggestions or []) if s]
        _last_ai_picked = None


def get_ai_suggestions() -> list[str]:
    with _lock:
        return list(_last_ai_suggestions)


def pick_ai_suggestion(index: int = 0) -> Optional[str]:
    """Memorizza la scelta. index 0-based (0 = prima suggerita)."""
    global _last_ai_picked
    with _lock:
        if not _last_ai_suggestions:
            return None
        idx = max(0, min(index, len(_last_ai_suggestions) - 1))
        _last_ai_picked = _last_ai_suggestions[idx]
        return _last_ai_picked


def get_picked_ai_suggestion() -> Optional[str]:
    with _lock:
        return _last_ai_picked

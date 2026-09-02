# actions/message_hud.py
# ---------------------------------------------------------------------------
# NEW (2026-01):
# Quando l'utente dice "Jarvis apri whatsapp" o "Jarvis apri instagram",
# NON aprire piu' l'app di sistema: mostra una piccola TENDINA HUD in alto a
# destra con i messaggi non letti della piattaforma richiesta.
#
# Il modulo delega il fetch dei messaggi ai poller esistenti in
# actions.check_messages ( _unread_whatsapp / _unread_instagram ) e delega
# la resa grafica al metodo `show_messages_panel(platform, messages)`
# esposto da `JarvisUI` (vedi ui.py).
# ---------------------------------------------------------------------------

from __future__ import annotations
from typing import Any

from actions.check_messages import _unread_whatsapp, _unread_instagram


_PLATFORMS = {
    "whatsapp":  _unread_whatsapp,
    "wa":        _unread_whatsapp,
    "instagram": _unread_instagram,
    "ig":        _unread_instagram,
    "insta":     _unread_instagram,
}


def is_hud_target(app_name: str) -> str:
    """Ritorna 'whatsapp' | 'instagram' | '' in base al nome app richiesto.

    Case-insensitive. Riconosce alias tipo 'wa', 'insta', ecc.
    """
    key = (app_name or "").strip().lower()
    if key in _PLATFORMS:
        return "whatsapp" if _PLATFORMS[key] is _unread_whatsapp else "instagram"
    if "whatsapp" in key or key == "wa":
        return "whatsapp"
    if "instagram" in key or "insta" in key:
        return "instagram"
    return ""


def open_messages_hud(platform: str, player: Any = None) -> str:
    """Fetch unread + apri la tendina HUD.

    Ritorna la stringa che JARVIS deve pronunciare.
    """
    plat = (platform or "").strip().lower()
    fetch = _PLATFORMS.get(plat)
    if not fetch:
        return f"Piattaforma non supportata: {platform}."

    try:
        msgs = fetch() or []
    except Exception:
        msgs = []

    # Delega alla UI il rendering della tendina.
    if player is not None and hasattr(player, "show_messages_panel"):
        try:
            player.show_messages_panel(plat, msgs)
        except Exception as e:
            print(f"[message_hud] UI panel error: {e}")

    label = "WhatsApp" if plat == "whatsapp" else "Instagram"
    n = len(msgs)
    if n == 0:
        return f"Signore, nessun messaggio non letto su {label}."
    if n == 1:
        who = (msgs[0].get("from") or "").strip() or "un contatto"
        return f"Signore, ha un messaggio non letto su {label}, da {who}."
    names = ", ".join((m.get("from") or "?") for m in msgs[:3])
    more = "" if n <= 3 else f", e altri {n - 3}"
    return f"Signore, ha {n} messaggi non letti su {label}: {names}{more}."

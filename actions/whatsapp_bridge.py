# actions/whatsapp_bridge.py
# Helper minimale per parlare con il bridge whatsapp-web.js locale.
# Il bridge HTTP gira su WHATSAPP_BRIDGE_URL (default http://127.0.0.1:8765)
# ed espone:
#   GET  /chats   -> lista chat
#   GET  /unread  -> messaggi non letti
#   POST /send    -> {to, text}  invio messaggio
# Vedi README.md per come configurare il bridge.

from __future__ import annotations
import os
import threading
import time
from pathlib import Path
import requests

# Carica il file .env della root cosi' WHATSAPP_BRIDGE_URL e' visibile.
try:
    from dotenv import load_dotenv  # type: ignore
    _ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
    if _ENV_PATH.is_file():
        load_dotenv(_ENV_PATH, override=False)
except Exception:
    pass

WA_BASE = os.environ.get("WHATSAPP_BRIDGE_URL", "http://127.0.0.1:8765")


def send_via_bridge(recipient: str, message: str) -> tuple[bool, str]:
    try:
        r = requests.post(
            f"{WA_BASE}/send",
            json={"to": recipient, "text": message},
            timeout=20,
        )
        ok = r.ok and (r.json().get("ok") is True)
        return ok, r.text
    except Exception as e:
        return False, f"ERR: {e}"


def start_incoming_poller(on_message):
    """on_message(from_name, body) viene chiamato per ogni messaggio
    arrivato nel feed /unread."""
    def _loop():
        seen = set()
        while True:
            try:
                r = requests.get(f"{WA_BASE}/unread", timeout=8)
                if r.ok:
                    for m in r.json().get("messages", []):
                        mid = m.get("id") or (m.get("from", "") + "|" + (m.get("body", "")[:40]))
                        if mid in seen:
                            continue
                        seen.add(mid)
                        if len(seen) > 500:
                            seen = set(list(seen)[-250:])
                        try:
                            on_message(m.get("from", ""), m.get("body", ""))
                        except Exception:
                            pass
            except Exception:
                pass
            time.sleep(8)
    threading.Thread(target=_loop, daemon=True).start()

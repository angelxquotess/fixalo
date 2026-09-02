# actions/check_messages.py  (versione estesa)
# Modifiche rispetto alla versione vecchia:
#   1) i poller estraggono ANCHE il corpo del messaggio e il tipo
#      (testo/vocale). _notify riceve body e kind.
#   2) se kind == 'voice' Jarvis dice "Signore, <X> le ha inviato un
#      messaggio vocale. Vuole che lo riproduca?" e memorizza l'URL/path
#      per la riproduzione successiva (comando "Jarvis riproduci il vocale").
#   3) se kind == 'text' Jarvis dice "Signore, nuovo messaggio <plat> da
#      <X>: <body>" (rispetto al vecchio "da X" senza contenuto).
#   4) IG poller usa la API RAW (private_request) per evitare il crash
#      pydantic v2 su media direct-notes (video_url con schema instagram://).
#   5) filtro self-message su WhatsApp e Instagram (heuristic from_me).
#   6) keyword "urgente / emergenza / chiamami / aiuto" -> Jarvis ripete
#      due volte e prefissa con "ATTENZIONE".
#   7) nuovo comando read_last_notifications(n) per "Jarvis leggimi le
#      ultime N notifiche".

from __future__ import annotations
import os
import re
import time
import threading
from pathlib import Path
from typing import Callable

import requests

try:
    from dotenv import load_dotenv  # type: ignore
    _ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
    if _ENV_PATH.is_file():
        load_dotenv(_ENV_PATH, override=False)
except Exception:
    pass

from actions.message_state import set_last_incoming, get_recent_notifications

WA_BASE = os.environ.get("WHATSAPP_BRIDGE_URL", "http://127.0.0.1:8765")

URGENT_RE = re.compile(r"\b(urgente|emergenza|chiamami|aiuto|help|urgent)\b", re.I)


def _shorten(s: str, n: int = 300) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[:n].rstrip() + "..."


# ---------------------------------------------------------------------------
# Notify wrapper
# ---------------------------------------------------------------------------

def _notify(speak: Callable[[str], None],
            on_new_message: Callable | None,
            platform: str, sender: str,
            body: str = "", kind: str = "text",
            audio_url: str = "", audio_path: str = "",
            msg_id: str = "") -> None:
    if not sender:
        return
    try:
        set_last_incoming(platform, sender, body=body, kind=kind,
                          audio_url=audio_url, audio_path=audio_path,
                          msg_id=msg_id)
    except Exception:
        pass
    # Se c'e' una callback registrata da JarvisLive, e' lei che si
    # occupa dell'annuncio vocale (via Gemini Live) e dell'animazione UI:
    # NON facciamo qui lo speak() per evitare il doppio annuncio.
    if on_new_message:
        try:
            # Firma estesa (preferita).
            on_new_message(platform, sender,
                           body=body, kind=kind,
                           audio_url=audio_url, audio_path=audio_path)
            return
        except TypeError:
            # Fallback alla firma vecchia (platform, sender).
            try:
                on_new_message(platform, sender)
                return
            except Exception:
                pass
        except Exception:
            pass
    # Nessuna callback: modalita' "stand-alone" -> annuncio diretto via speak().
    plat_label = platform.capitalize()
    urgent = bool(body and URGENT_RE.search(body))
    prefix = "ATTENZIONE, " if urgent else ""
    try:
        if kind == "voice":
            line = (f"{prefix}Signore, {sender} le ha inviato un messaggio "
                    f"vocale su {plat_label}. Vuole che lo riproduca?")
        elif body:
            line = (f"{prefix}Signore, nuovo messaggio {plat_label} da "
                    f"{sender}. Vuole sapere il contenuto?")
        else:
            line = (f"{prefix}Signore, nuovo messaggio {plat_label} da "
                    f"{sender}")
        speak(line)
        if urgent:
            time.sleep(0.6)
            speak(line)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------

def _wa_extract(m: dict) -> tuple[str, str, str, str, str]:
    """Ritorna (sender, body, kind, audio_url, msg_id). Filtra self-msg."""
    if m.get("fromMe") or m.get("from_me"):
        return ("", "", "", "", "")
    sender = (m.get("notifyName") or m.get("pushname") or
              m.get("from", "") or "qualcuno")
    msg_id = str(m.get("id") or "")
    mtype = (m.get("type") or "").lower()
    body  = m.get("body") or m.get("text") or ""
    audio = ""
    kind  = "text"
    if mtype in ("ptt", "audio") or m.get("isVoice"):
        kind = "voice"
        # URL/endpoint di download del media dal bridge esteso
        audio = m.get("mediaUrl") or (f"{WA_BASE}/media/{msg_id}" if msg_id else "")
    elif mtype == "image":
        kind = "image"
    elif mtype == "video":
        kind = "video"
    elif mtype == "sticker":
        kind = "sticker"
    return (sender, body, kind, audio, msg_id)


def _poll_whatsapp(speak, on_new_message) -> None:
    last_ids: set[str] = set()
    first_pass = True
    while True:
        try:
            r = requests.get(f"{WA_BASE}/unread", timeout=8)
            if r.ok:
                for m in r.json().get("messages", []):
                    mid = m.get("id") or (m.get("from", "") + "|" + (m.get("body", "")[:40]))
                    if mid in last_ids:
                        continue
                    last_ids.add(mid)
                    if len(last_ids) > 300:
                        last_ids = set(list(last_ids)[-150:])
                    if first_pass:
                        continue
                    sender, body, kind, audio, msg_id = _wa_extract(m)
                    if not sender:
                        continue
                    _notify(speak, on_new_message, "whatsapp",
                            sender, body=body, kind=kind,
                            audio_url=audio, msg_id=msg_id)
            first_pass = False
        except Exception:
            pass
        time.sleep(10)


# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------

def _poll_discord(speak, on_new_message) -> None:
    tok = os.environ.get("DISCORD_USER_TOKEN")
    if not tok:
        return
    headers = {"Authorization": tok}
    last_ids: dict[str, str] = {}
    first_pass = True
    me_id = ""
    try:
        rm = requests.get("https://discord.com/api/v9/users/@me",
                          headers=headers, timeout=6)
        if rm.ok:
            me_id = str(rm.json().get("id") or "")
    except Exception:
        pass
    while True:
        try:
            r = requests.get("https://discord.com/api/v9/users/@me/channels",
                             headers=headers, timeout=8)
            if r.ok:
                for ch in r.json()[:15]:
                    if ch.get("type") != 1:
                        continue
                    ch_id = ch.get("id")
                    u = (ch.get("recipients") or [{}])[0]
                    name = u.get("global_name") or u.get("username") or "DM"
                    try:
                        mr = requests.get(
                            f"https://discord.com/api/v9/channels/{ch_id}/messages?limit=1",
                            headers=headers, timeout=8,
                        )
                        if mr.ok and mr.json():
                            msg = mr.json()[0]
                            mid = str(msg.get("id", ""))
                            prev = last_ids.get(ch_id)
                            last_ids[ch_id] = mid
                            if not (prev and prev != mid) or first_pass:
                                continue
                            author = (msg.get("author") or {})
                            if me_id and str(author.get("id")) == me_id:
                                continue
                            content = msg.get("content") or ""
                            atts = msg.get("attachments") or []
                            kind = "text"
                            audio = ""
                            if atts:
                                a0 = atts[0]
                                ct = (a0.get("content_type") or "").lower()
                                if ct.startswith("audio") or a0.get("filename", "").lower().endswith((".ogg", ".mp3", ".m4a", ".wav", ".opus")):
                                    kind = "voice"
                                    audio = a0.get("url", "")
                            _notify(speak, on_new_message, "discord", name,
                                    body=content, kind=kind,
                                    audio_url=audio, msg_id=mid)
                    except Exception:
                        continue
            first_pass = False
        except Exception:
            pass
        time.sleep(15)


# ---------------------------------------------------------------------------
# Telegram (event-driven via Telethon)
# ---------------------------------------------------------------------------

def _poll_telegram(speak, on_new_message) -> None:
    api_id   = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    if not (api_id and api_hash):
        return
    try:
        from telethon import TelegramClient, events
        import asyncio, tempfile
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = TelegramClient(str(Path.home() / ".jarvis_tg"),
                                int(api_id), api_hash, loop=loop)

        @client.on(events.NewMessage(incoming=True))
        async def _handler(event):
            try:
                if event.out:
                    return
                sender = await event.get_sender()
                # SOLO profili utente (no bot, no canali, no gruppi)
                from telethon.tl.types import User
                if not isinstance(sender, User):
                    return
                if getattr(sender, "bot", False):
                    return
                name = (getattr(sender, "first_name", "") or
                        getattr(sender, "username", "") or "qualcuno")
                msg = event.message
                kind = "text"
                body = msg.message or ""
                audio_path = ""
                if msg.voice or (msg.media and getattr(msg.media, "document", None) and
                                 any(getattr(a, "voice", False)
                                     for a in (msg.media.document.attributes or []))):
                    kind = "voice"
                    try:
                        dest = Path(tempfile.gettempdir()) / f"jarvis_tg_{msg.id}.ogg"
                        await msg.download_media(file=str(dest))
                        audio_path = str(dest)
                    except Exception:
                        audio_path = ""
                _notify(speak, on_new_message, "telegram", name,
                        body=body, kind=kind, audio_path=audio_path,
                        msg_id=str(msg.id))
            except Exception:
                pass

        client.start()
        client.run_until_disconnected()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Instagram (RAW API per evitare crash pydantic v2 su direct-notes)
# ---------------------------------------------------------------------------

def _poll_instagram(speak, on_new_message) -> None:
    sess = Path.home() / ".jarvis_ig.json"
    if not sess.is_file():
        return
    last_ids: dict[str, str] = {}
    first_pass = True
    cl = None
    my_pk = ""
    while True:
        try:
            if cl is None:
                from instagrapi import Client
                cl = Client()
                cl.load_settings(str(sess))
                try:
                    me = cl.private_request("accounts/current_user/")
                    my_pk = str((me or {}).get("user", {}).get("pk") or "")
                except Exception:
                    my_pk = ""
            resp = cl.private_request("direct_v2/inbox/", params={
                "visual_message_return_type": "unseen",
                "thread_message_limit": "1",
                "persistentBadging": "true",
                "limit": "20",
            }) or {}
            threads = (resp.get("inbox") or {}).get("threads") or []
            for t in threads:
                tid = t.get("thread_id") or t.get("thread_v2_id")
                if not tid:
                    continue
                items = t.get("items") or []
                last_msg = items[0] if items else None
                mid = str((last_msg or {}).get("item_id") or "")
                prev = last_ids.get(str(tid))
                last_ids[str(tid)] = mid
                if not (mid and prev and prev != mid) or first_pass:
                    continue
                # self filter
                sender_pk = str((last_msg or {}).get("user_id") or "")
                if my_pk and sender_pk == my_pk:
                    continue
                users = t.get("users") or []
                label = ", ".join((u.get("username", "") for u in users)) or "qualcuno"
                kind = "text"
                body = ""
                audio = ""
                itype = (last_msg or {}).get("item_type") or ""
                if itype == "text":
                    body = (last_msg or {}).get("text") or ""
                elif itype in ("voice_media", "direct-audio", "audio"):
                    kind = "voice"
                    vm = (last_msg or {}).get("voice_media") or {}
                    media = vm.get("media") or {}
                    audio_versions = ((media.get("audio") or {})
                                      .get("audio_src_versions") or [])
                    if not audio_versions:
                        audio_versions = [media.get("audio") or {}]
                    for av in audio_versions:
                        u = av.get("url") or av.get("audio_src") or ""
                        if u.startswith("http"):
                            audio = u
                            break
                elif itype == "media":
                    kind = "image"
                elif itype == "media_share":
                    body = "[post condiviso]"
                else:
                    body = f"[{itype}]"
                _notify(speak, on_new_message, "instagram", label,
                        body=body, kind=kind, audio_url=audio, msg_id=mid)
            first_pass = False
        except Exception:
            cl = None  # forza re-init alla prossima iterazione
        time.sleep(20)


# ---------------------------------------------------------------------------
# Comandi pubblici
# ---------------------------------------------------------------------------

def read_last_notifications(parameters: dict | None = None, response=None,
                            player=None, session_memory=None) -> str:
    """Comando 'Jarvis leggimi le ultime N notifiche'."""
    params = parameters or {}
    try:
        n = int(params.get("count") or params.get("n") or 5)
    except Exception:
        n = 5
    items = get_recent_notifications(n)
    if not items:
        return "Nessuna notifica recente, signore."
    lines = []
    for it in items:
        plat = (it.get("platform") or "").capitalize()
        snd  = it.get("sender") or "?"
        knd  = it.get("kind") or "text"
        if knd == "voice":
            lines.append(f"{plat}, {snd}: messaggio vocale.")
        else:
            body = _shorten(it.get("body") or "", 200)
            lines.append(f"{plat}, {snd}: {body}" if body else f"{plat}, {snd}.")
    text = "Ecco le ultime " + str(len(lines)) + " notifiche, signore. " + " ".join(lines)
    if player and hasattr(player, "write_log"):
        try: player.write_log("[notifiche] " + text)
        except Exception: pass
    return text


# ---------------------------------------------------------------------------
# Snapshot non-letti (per il comando "ho messaggi?") - INVARIATO interfaccia
# ---------------------------------------------------------------------------

def _unread_whatsapp() -> list[dict]:
    try:
        r = requests.get(f"{WA_BASE}/unread", timeout=4)
        if not r.ok: return []
        return [{"from": m.get("from", ""), "body": m.get("body", "")}
                for m in r.json().get("messages", [])]
    except Exception:
        return []


def _unread_telegram() -> list[dict]:
    try:
        api_id   = os.environ.get("TELEGRAM_API_ID")
        api_hash = os.environ.get("TELEGRAM_API_HASH")
        if not (api_id and api_hash): return []
        from telethon.sync import TelegramClient
        client = TelegramClient(str(Path.home() / ".jarvis_tg"), int(api_id), api_hash)
        client.connect()
        if not client.is_user_authorized():
            client.disconnect(); return []
        out = []
        for d in client.iter_dialogs(limit=200):
            unread = getattr(d, "unread_count", 0) or 0
            if unread <= 0: continue
            name = getattr(d, "name", None) or getattr(d, "title", "")
            last = ""
            try:
                m = getattr(d, "message", None)
                if m is not None: last = (getattr(m, "text", "") or "")[:120]
            except Exception: pass
            out.append({"from": name, "count": unread, "body": last})
        client.disconnect()
        return out
    except Exception:
        return []


def _unread_discord() -> list[dict]:
    try:
        tok = os.environ.get("DISCORD_USER_TOKEN")
        if not tok: return []
        headers = {"Authorization": tok}; out = []
        r = requests.get("https://discord.com/api/v9/users/@me/channels",
                         headers=headers, timeout=6)
        if not r.ok: return []
        for ch in r.json()[:10]:
            if ch.get("type") != 1: continue
            ch_id = ch.get("id")
            u = (ch.get("recipients") or [{}])[0]
            name = u.get("global_name") or u.get("username") or "DM"
            try:
                mr = requests.get(
                    f"https://discord.com/api/v9/channels/{ch_id}/messages?limit=1",
                    headers=headers, timeout=6)
                if mr.ok and mr.json():
                    msg = mr.json()[0]
                    out.append({"from": name, "body": (msg.get("content") or "")[:120]})
            except Exception: continue
        return out
    except Exception:
        return []


def _unread_instagram() -> list[dict]:
    try:
        sess = Path.home() / ".jarvis_ig.json"
        if not sess.is_file(): return []
        from instagrapi import Client
        cl = Client(); cl.load_settings(str(sess))
        resp = cl.private_request("direct_v2/inbox/", params={
            "visual_message_return_type": "unseen",
            "thread_message_limit": "1",
            "limit": "20",
        }) or {}
        threads = (resp.get("inbox") or {}).get("threads") or []
        out = []
        for t in threads:
            users = t.get("users") or []
            label = ", ".join((u.get("username", "") for u in users)) or "(thread)"
            items = t.get("items") or []
            last = ""
            if items and items[0].get("item_type") == "text":
                last = (items[0].get("text") or "")[:120]
            out.append({"from": label, "body": last})
        return out
    except Exception:
        return []


def gather_unread() -> dict:
    return {
        "whatsapp":  _unread_whatsapp(),
        "telegram":  _unread_telegram(),
        "discord":   _unread_discord(),
        "instagram": _unread_instagram(),
    }


def summarize_unread(data: dict | None = None) -> str:
    data = data or gather_unread()
    parts = []; total = 0
    for plat, items in data.items():
        if not items: continue
        n = sum(int(it.get("count", 1)) for it in items)
        total += n
        names = ", ".join((it.get("from", "") or "?") for it in items[:5])
        parts.append(f"{plat.capitalize()}: {n} ({names})")
    if not parts:
        return "Nessun messaggio non letto, signore."
    return "Hai " + str(total) + " messaggi non letti - " + " | ".join(parts)


def check_messages(parameters: dict | None = None, response=None,
                   player=None, session_memory=None) -> str:
    data = gather_unread()
    text = summarize_unread(data)
    if player and hasattr(player, "write_log"):
        try: player.write_log("[messages] " + text)
        except Exception: pass
    return text


# ---------------------------------------------------------------------------
# Poller bootstrap
# ---------------------------------------------------------------------------

_started = False
_lock = threading.Lock()


def start_notification_pollers(
    speak: Callable[[str], None],
    on_new_message: Callable[[str, str], None] | None = None,
) -> None:
    global _started
    with _lock:
        if _started: return
        _started = True
    threading.Thread(target=_poll_whatsapp,  args=(speak, on_new_message), daemon=True).start()
    threading.Thread(target=_poll_discord,   args=(speak, on_new_message), daemon=True).start()
    threading.Thread(target=_poll_telegram,  args=(speak, on_new_message), daemon=True).start()
    threading.Thread(target=_poll_instagram, args=(speak, on_new_message), daemon=True).start()

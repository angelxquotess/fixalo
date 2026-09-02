# actions/send_dashboard.py
# Dashboard JARVIS - invio messaggi cross-platform via TOKEN/API.
#
# Comando vocale: "Jarvis invia un messaggio" -> apre la dashboard.
#
# Novita' di questa edizione:
#   * tema HUD sci-fi JARVIS (palette ciano #00d4ff su sfondo #00060a,
#     font Courier New, bordi luminosi) - coerente con la "GUI iniziale"
#   * barra di ricerca per filtrare TUTTE le chat scritte (live filter
#     mentre digiti, in aggiunta alla scansione automatica)
#   * pulsanti "LOGIN" integrati per ogni piattaforma:
#         - WhatsApp  -> apre il bridge whatsapp-web.js (QR-code)
#         - Telegram  -> wizard phone + code via Telethon
#         - Instagram -> form user + pwd + 2FA opzionale via instagrapi
#         - Discord   -> dialogo per incollare l'user-token
#   * fix invio: mapping name -> id/jid mantenuto in memoria, cosi'
#     l'invio raggiunge davvero la chat selezionata (era il vero motivo
#     per cui WhatsApp / Instagram NON inviavano dopo aver fatto l'accesso)
#
# La GUI PyQt6 viene SEMPRE lanciata in un processo separato via
#   `python -m actions.send_dashboard`
# per evitare il crash "QObject: Cannot create children for a parent
# that is in a different thread" tipico di asyncio+Qt.

from __future__ import annotations
import os
import sys
import json
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional, Any

import requests

# Carica .env della root del progetto (DISCORD_USER_TOKEN, TELEGRAM_API_ID,
# TELEGRAM_API_HASH, WHATSAPP_BRIDGE_URL, ...) anche nel subprocess.
try:
    from dotenv import load_dotenv, set_key  # type: ignore
    _ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
    if _ENV_PATH.is_file():
        load_dotenv(_ENV_PATH, override=False)
except Exception:
    _ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
    set_key = None  # type: ignore

PLATFORMS = ["whatsapp", "telegram", "discord", "instagram"]
PLATFORM_LABEL = {
    "whatsapp":  "WhatsApp",
    "telegram":  "Telegram",
    "discord":   "Discord",
    "instagram": "Instagram",
}

WA_BASE = os.environ.get("WHATSAPP_BRIDGE_URL", "http://127.0.0.1:8765")
WA_BRIDGE_DIR = Path(__file__).resolve().parent.parent / "wa-bridge"
IG_SESSION = Path.home() / ".jarvis_ig.json"
TG_SESSION = Path.home() / ".jarvis_tg"

# Mappa runtime "name visualizzato" -> identificatore reale (jid/user_id/...)
# riempita durante la scansione e usata in fase di invio. E' l'unica
# struttura *globale* perche' GUI + scanner + sender vivono nello stesso
# processo subprocess.
_ID_MAP: dict[str, dict[str, str]] = {p: {} for p in PLATFORMS}


def _persist_env(key: str, value: str) -> None:
    """Salva una chiave nel .env della root (best-effort)."""
    try:
        _ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not _ENV_PATH.exists():
            _ENV_PATH.write_text("", encoding="utf-8")
        if set_key is not None:
            set_key(str(_ENV_PATH), key, value)
        os.environ[key] = value
    except Exception:
        os.environ[key] = value


# ---------------------------------------------------------------------------
# SCANSIONE CHAT  (token / session - niente apertura di app)
# I scanner ritornano (lista_nomi, diag_text) cosi' l'UI puo' spiegare
# all'utente PERCHE' la lista e' vuota (bridge offline, QR non scansionato,
# sessione scaduta, ecc).
# ---------------------------------------------------------------------------

def _scan_whatsapp_chats() -> tuple[list[str], str]:
    # Stato del bridge: serve a distinguere "bridge offline" da
    # "bridge ok ma WhatsApp non ancora collegato".
    ready = None
    try:
        rs = requests.get(f"{WA_BASE}/status", timeout=4)
        if rs.ok:
            js = rs.json()
            ready = bool(js.get("ready"))
            br_err = js.get("error")
            if ready is False:
                base = "Bridge attivo ma WhatsApp NON collegato."
                if br_err:
                    return [], f"{base} Errore bridge: {br_err}"
                return [], f"{base} Scansiona il QR nel terminale del bridge (wa-bridge)."
    except Exception:
        return [], f"Bridge WhatsApp irraggiungibile su {WA_BASE}. Avvia 'cd wa-bridge && npm start'."
    try:
        r = requests.get(f"{WA_BASE}/chats", timeout=15)
        if not r.ok:
            return [], f"Bridge HTTP {r.status_code} su /chats."
        data = r.json().get("chats") or []
        names: list[str] = []
        for c in data:
            if isinstance(c, str):
                names.append(c)
            else:
                name = c.get("name") or c.get("id") or ""
                chat_id = c.get("id") or c.get("chatId") or name
                if name:
                    names.append(name)
                    _ID_MAP["whatsapp"][name] = str(chat_id)
        if not names:
            return [], "Bridge connesso ma 0 chat (account vuoto?)."
        return names, f"OK: {len(names)} chat caricate dal bridge."
    except Exception as e:
        return [], f"Errore lettura chat WhatsApp: {e}"


def _telegram_client():
    api_id   = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    if not (api_id and api_hash):
        return None
    try:
        from telethon.sync import TelegramClient
    except Exception:
        return None
    try:
        client = TelegramClient(str(TG_SESSION), int(api_id), api_hash)
        client.connect()
        if not client.is_user_authorized():
            client.disconnect()
            return None
        return client
    except Exception:
        return None


def _tg_is_user_profile(entity) -> bool:
    """True solo se l'entita' Telegram e' un profilo utente reale (non bot,
    non gruppo, non canale, non sistema)."""
    if entity is None:
        return False
    # Telethon: solo User ha l'attributo `bot`. Channel/Chat non ce l'hanno.
    if not hasattr(entity, "bot"):
        return False
    if getattr(entity, "bot", False):
        return False
    # esclude account di servizio / cancellati / supportati come "user" ma non profili
    if getattr(entity, "deleted", False):
        return False
    if getattr(entity, "support", False):
        return False
    return True


def _scan_telegram_chats() -> tuple[list[str], str]:
    api_id   = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    if not (api_id and api_hash):
        return [], "TELEGRAM_API_ID / TELEGRAM_API_HASH non impostati. Fai LOGIN TE."
    client = _telegram_client()
    if client is None:
        return [], "Sessione Telegram assente o non autorizzata. Fai LOGIN TE."
    try:
        names = []
        for d in client.iter_dialogs(limit=500):
            ent = getattr(d, "entity", None)
            if not _tg_is_user_profile(ent):
                continue
            n = getattr(d, "name", None) or getattr(d, "title", "")
            if n:
                names.append(n)
                if getattr(ent, "id", None) is not None:
                    _ID_MAP["telegram"][n] = str(ent.id)
        if not names:
            return [], "Telegram autorizzato ma nessun profilo utente."
        return names, f"OK: {len(names)} profili Telegram."
    except Exception as e:
        return [], f"Errore Telegram: {e}"
    finally:
        try: client.disconnect()
        except Exception: pass


def _scan_discord_chats() -> tuple[list[str], str]:
    tok = os.environ.get("DISCORD_USER_TOKEN")
    if not tok:
        return [], "DISCORD_USER_TOKEN mancante. Fai LOGIN DI."
    headers = {"Authorization": tok}
    names: list[str] = []
    try:
        r = requests.get("https://discord.com/api/v9/users/@me/channels",
                         headers=headers, timeout=10)
        if not r.ok:
            return [], f"Discord HTTP {r.status_code} (token scaduto?)."
        for ch in r.json():
            if ch.get("type") == 1:
                u = (ch.get("recipients") or [{}])[0]
                label = u.get("global_name") or u.get("username") or ""
                if label:
                    full = "DM: " + label
                    names.append(full)
                    _ID_MAP["discord"][full] = ch.get("id") or ""
            elif ch.get("type") == 3:
                full = "Gruppo: " + (ch.get("name") or "DM")
                names.append(full)
                _ID_MAP["discord"][full] = ch.get("id") or ""
        if not names:
            return [], "Discord: 0 DM trovati."
        return names, f"OK: {len(names)} canali Discord."
    except Exception as e:
        return [], f"Errore Discord: {e}"


def _instagram_client_and_diag():
    """Ritorna (cl, diag_or_None). cl=None se sessione assente/invalida."""
    if not IG_SESSION.is_file():
        return None, f"Sessione Instagram assente ({IG_SESSION}). Fai LOGIN IN."
    try:
        from instagrapi import Client
    except Exception as e:
        return None, f"instagrapi non installato: {e}"
    try:
        cl = Client()
        cl.load_settings(str(IG_SESSION))
    except Exception as e:
        return None, f"Sessione IG corrotta: {e}. Rifai LOGIN IN."
    # validazione: senza questa, direct_threads puo' tornare vuoto su sessione scaduta
    try:
        cl.account_info()
        return cl, None
    except Exception as e:
        return None, f"Sessione IG scaduta o non valida ({e}). Rifai LOGIN IN."


def _instagram_client():
    cl, _ = _instagram_client_and_diag()
    return cl


def _scan_instagram_chats() -> tuple[list[str], str]:
    cl, diag = _instagram_client_and_diag()
    if cl is None:
        return [], diag or "Instagram non disponibile."
    # Bug noto di instagrapi: con pydantic v2 alcuni media tipo "direct-notes"
    # hanno video_url con schema custom instagram:// (non http/https) e il
    # validator crasha (MediaXma.video_url). Bypassiamo il problema usando
    # l'API raw di instagrapi (private_request) senza model parsing.
    threads_raw: list[dict] = []
    try:
        cursor = None
        for _ in range(10):  # paginazione di sicurezza
            params: dict[str, str] = {
                "visual_message_return_type": "unseen",
                "thread_message_limit": "1",
                "persistentBadging": "true",
                "limit": "20",
            }
            if cursor:
                params["cursor"] = cursor
            resp = cl.private_request("direct_v2/inbox/", params=params) or {}
            inbox = resp.get("inbox") or {}
            page = inbox.get("threads") or []
            threads_raw.extend(page)
            if len(threads_raw) >= 100:
                break
            if not inbox.get("has_older"):
                break
            cursor = inbox.get("oldest_cursor")
            if not cursor:
                break
    except Exception as e:
        return [], f"Errore direct_threads: {e}. Prova a rifare LOGIN IN."
    out = []
    for t in threads_raw:
        users = t.get("users") or []
        label = ", ".join((u.get("username", "") or "" for u in users)) or "(thread)"
        out.append(label)
        user_ids = [str(u.get("pk", "") or u.get("user_id", ""))
                    for u in users if u.get("pk") or u.get("user_id")]
        tid = t.get("thread_id") or t.get("thread_v2_id")
        _ID_MAP["instagram"][label] = json.dumps({
            "user_ids": [x for x in user_ids if x],
            "thread_id": str(tid or ""),
        })
    if not out:
        return [], "Instagram autenticato ma 0 conversazioni dirette."
    return out, f"OK: {len(out)} thread Instagram."


SCANNERS: dict[str, Callable[[], tuple[list[str], str]]] = {
    "whatsapp":  _scan_whatsapp_chats,
    "telegram":  _scan_telegram_chats,
    "discord":   _scan_discord_chats,
    "instagram": _scan_instagram_chats,
}


# ---------------------------------------------------------------------------
# INVIO  (solo via API/token, niente app/sito)
# ---------------------------------------------------------------------------

def _send_whatsapp(recipient: str, text: str) -> str:
    # se conosciamo l'id reale dalla scansione lo usiamo, altrimenti
    # passiamo il nome al bridge che prova a risolverlo.
    target = _ID_MAP["whatsapp"].get(recipient, recipient)
    try:
        r = requests.post(f"{WA_BASE}/send",
                          json={"to": target, "name": recipient, "text": text},
                          timeout=25)
        try: payload = r.json()
        except Exception: payload = {}
        if r.ok and payload.get("ok") is True:
            return f"WhatsApp -> {recipient}: inviato"
        return f"WhatsApp -> {recipient}: bridge {r.status_code} {payload.get('error','')}"
    except Exception as e:
        return f"WhatsApp -> {recipient}: errore bridge {e}"


def _send_telegram(recipient: str, text: str) -> str:
    client = _telegram_client()
    if client is None:
        return f"Telegram -> {recipient}: sessione/credenziali assenti (fai LOGIN)"
    try:
        target = None
        # 1) prova via id memorizzato dalla scansione
        cached = _ID_MAP["telegram"].get(recipient)
        if cached:
            try:    target = client.get_entity(int(cached))
            except Exception:
                try: target = client.get_entity(cached)
                except Exception: target = None
            if not _tg_is_user_profile(target):
                target = None
        # 2) cerca per nome esatto / parziale (solo profili utente, no bot/gruppi/canali)
        if target is None:
            for d in client.iter_dialogs(limit=500):
                ent = getattr(d, "entity", None)
                if not _tg_is_user_profile(ent):
                    continue
                n = getattr(d, "name", None) or getattr(d, "title", "")
                if n and recipient.lower() in n.lower():
                    target = ent
                    if n.lower() == recipient.lower():
                        break
        # 3) prova come @username (solo se risolve a un profilo utente reale)
        if target is None:
            try:
                cand = client.get_entity(recipient)
                if _tg_is_user_profile(cand):
                    target = cand
            except Exception:
                target = None
        if target is None:
            return f"Telegram -> {recipient}: profilo utente non trovato (bot/gruppi/canali esclusi)"
        client.send_message(target, text)
        return f"Telegram -> {recipient}: inviato"
    except Exception as e:
        return f"Telegram -> {recipient}: errore {e}"
    finally:
        try: client.disconnect()
        except Exception: pass


def _send_discord(recipient: str, text: str) -> str:
    tok = os.environ.get("DISCORD_USER_TOKEN")
    if not tok:
        return f"Discord -> {recipient}: DISCORD_USER_TOKEN non impostato (fai LOGIN)"
    headers = {"Authorization": tok, "Content-Type": "application/json"}
    channel_id: str | None = _ID_MAP["discord"].get(recipient)
    try:
        if not channel_id:
            if recipient.isdigit():
                channel_id = recipient
            else:
                label = recipient.split(":", 1)[-1].strip().lower()
                r = requests.get("https://discord.com/api/v9/users/@me/channels",
                                 headers=headers, timeout=10)
                if r.ok:
                    for ch in r.json():
                        if ch.get("type") == 1:
                            u = (ch.get("recipients") or [{}])[0]
                            name = (u.get("global_name") or u.get("username") or "").lower()
                            if name == label:
                                channel_id = ch.get("id")
                                break
        if not channel_id:
            return f"Discord -> {recipient}: canale non trovato"
        r = requests.post(
            f"https://discord.com/api/v9/channels/{channel_id}/messages",
            headers=headers, json={"content": text}, timeout=15,
        )
        if r.ok:
            return f"Discord -> {recipient}: inviato"
        return f"Discord -> {recipient}: HTTP {r.status_code}"
    except Exception as e:
        return f"Discord -> {recipient}: errore {e}"


def _send_instagram(recipient: str, text: str) -> str:
    cl = _instagram_client()
    if cl is None:
        return f"Instagram -> {recipient}: sessione assente (fai LOGIN)"
    try:
        cached = _ID_MAP["instagram"].get(recipient)
        user_ids: list[int] = []
        thread_id: str = ""
        if cached:
            try:
                meta = json.loads(cached)
                user_ids = [int(x) for x in meta.get("user_ids", []) if str(x).isdigit()]
                thread_id = str(meta.get("thread_id") or "")
            except Exception:
                pass
        if thread_id:
            try:
                cl.direct_send(text, thread_ids=[int(thread_id)])
                return f"Instagram -> {recipient}: inviato"
            except Exception:
                pass
        if not user_ids:
            # fallback: ricava da username
            username = recipient.lstrip("@").split(",")[0].strip()
            user_ids = [int(cl.user_id_from_username(username))]
        cl.direct_send(text, user_ids=user_ids)
        return f"Instagram -> {recipient}: inviato"
    except Exception as e:
        return f"Instagram -> {recipient}: errore {e}"


def _dispatch(platform: str, recipient: str, text: str) -> str:
    p = (platform or "").lower()
    if p == "whatsapp":  return _send_whatsapp(recipient, text)
    if p == "telegram":  return _send_telegram(recipient, text)
    if p == "discord":   return _send_discord(recipient, text)
    if p == "instagram": return _send_instagram(recipient, text)
    return f"{platform}/{recipient}: piattaforma non supportata"


def send_to_targets(targets: list[tuple[str, str]], text: str,
                    on_log: Callable[[str], None] | None = None) -> list[str]:
    out: list[str] = []
    for platform, recipient in targets:
        try:
            r = _dispatch(platform, recipient, text)
        except Exception as e:
            r = f"{platform}/{recipient}: errore {e}"
        out.append(r)
        if on_log:
            try: on_log(r)
            except Exception: pass
    return out


# ---------------------------------------------------------------------------
# LOGIN  (eseguito direttamente dalla dashboard, non piu' script separati)
# ---------------------------------------------------------------------------

def _wa_status() -> dict:
    """Ritorna {ready, qr, online} dal bridge."""
    try:
        r = requests.get(f"{WA_BASE}/status", timeout=3)
        if r.ok:
            js = r.json()
            return {"online": True, "ready": bool(js.get("ready")), "qr": js.get("qr")}
        return {"online": True, "ready": False, "qr": None}
    except Exception:
        return {"online": False, "ready": False, "qr": None}


def _wa_bridge_running() -> bool:
    return _wa_status()["online"]


def _wa_login_start() -> tuple[bool, str]:
    """Avvia il bridge whatsapp-web.js locale (se non gia' attivo).
    Restituisce (ok, messaggio per l'utente). Il QR-code apparira'
    nella console del bridge."""
    if _wa_bridge_running():
        return True, "Bridge WhatsApp gia' attivo - se non sei loggato, scansiona il QR nel terminale del bridge."
    if not WA_BRIDGE_DIR.is_dir():
        return False, f"Cartella {WA_BRIDGE_DIR} mancante - reinstalla il progetto."
    try:
        if sys.platform.startswith("win"):
            cmd = ["cmd", "/c", "npm start"]
            creationflags = 0x00000010  # CREATE_NEW_CONSOLE: il QR e' visibile
            subprocess.Popen(cmd, cwd=str(WA_BRIDGE_DIR), creationflags=creationflags)
        else:
            subprocess.Popen(["npm", "start"], cwd=str(WA_BRIDGE_DIR),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        return True, ("Bridge WhatsApp avviato. Apri il terminale del bridge, scansiona "
                      "il QR-code con il telefono (WhatsApp > Dispositivi collegati). "
                      "Poi premi di nuovo Scansiona chat.")
    except FileNotFoundError:
        return False, "Node.js non trovato (serve npm in PATH)."
    except Exception as e:
        return False, f"Avvio bridge fallito: {e}"


def _tg_login(api_id: str, api_hash: str, phone: str,
              code_provider: Callable[[], str],
              password_provider: Callable[[], str] | None = None) -> tuple[bool, str]:
    if not (api_id and api_hash and phone):
        return False, "Compila API ID, API HASH e numero di telefono."
    try:
        from telethon.sync import TelegramClient
        from telethon.errors import SessionPasswordNeededError
    except Exception:
        return False, "telethon non installato."
    try:
        client = TelegramClient(str(TG_SESSION), int(api_id), api_hash)
        client.connect()
        if not client.is_user_authorized():
            client.send_code_request(phone)
            code = code_provider()
            try:
                client.sign_in(phone, code)
            except SessionPasswordNeededError:
                pwd = password_provider() if password_provider else ""
                client.sign_in(password=pwd)
        ok = client.is_user_authorized()
        client.disconnect()
        if ok:
            _persist_env("TELEGRAM_API_ID", api_id)
            _persist_env("TELEGRAM_API_HASH", api_hash)
            return True, "Telegram autenticato (sessione salvata)."
        return False, "Autenticazione Telegram non confermata."
    except Exception as e:
        return False, f"Errore login Telegram: {e}"


def _ig_login(username: str, password: str, code_2fa: str = "") -> tuple[bool, str]:
    if not (username and password):
        return False, "Username e password obbligatori."
    try:
        from instagrapi import Client
        from instagrapi.exceptions import TwoFactorRequired, ChallengeRequired, BadPassword
    except Exception:
        return False, "instagrapi non installato."
    try:
        cl = Client()
        try:
            if code_2fa:
                cl.login(username, password, verification_code=code_2fa)
            else:
                cl.login(username, password)
        except TwoFactorRequired:
            if not code_2fa:
                return False, "2FA richiesto: inserisci anche il codice e riprova."
            cl.login(username, password, verification_code=code_2fa)
        except BadPassword:
            return False, "Password errata."
        except ChallengeRequired:
            return False, "Instagram chiede una verifica nell'app. Conferma e riprova."
        IG_SESSION.parent.mkdir(parents=True, exist_ok=True)
        cl.dump_settings(str(IG_SESSION))
        return True, f"Instagram autenticato come @{username}."
    except Exception as e:
        return False, f"Errore login Instagram: {e}"


def _dc_save_token(token: str) -> tuple[bool, str]:
    token = (token or "").strip()
    if len(token) < 30:
        return False, "Token troppo corto (sembra invalido)."
    _persist_env("DISCORD_USER_TOKEN", token)
    return True, "Token Discord salvato."


# ---------------------------------------------------------------------------
# CLI fallback
# ---------------------------------------------------------------------------

def _open_dashboard_cli(initial_text: str = "") -> list[str]:
    print("\n=== JARVIS: Dashboard Invio Messaggi (CLI) ===\n")
    print("Piattaforme: " + ", ".join(PLATFORM_LABEL.values()))
    raw = input("Quali piattaforme? (whatsapp,telegram,discord,instagram) > ").strip()
    chosen = [p.strip().lower() for p in raw.split(",") if p.strip() in PLATFORMS]
    if not chosen:
        print("Nessuna piattaforma valida.")
        return []
    targets: list[tuple[str, str]] = []
    for p in chosen:
        print(f"\n--- Scansione {PLATFORM_LABEL[p]}...")
        names, diag = SCANNERS[p]()
        print(f"  {diag}")
        if not names:
            r = input(f"  destinatario manuale {PLATFORM_LABEL[p]} > ").strip()
            if r: targets.append((p, r))
            continue
        for i, n in enumerate(names, 1):
            print(f"  {i:3d}. {n}")
        picks = input(f"Indici per {PLATFORM_LABEL[p]} (es. 1,3,7) > ").strip()
        for tok in picks.split(","):
            tok = tok.strip()
            if tok.isdigit():
                idx = int(tok) - 1
                if 0 <= idx < len(names):
                    targets.append((p, names[idx]))
    if not targets:
        print("Nessun destinatario selezionato.")
        return []
    text = initial_text or input("\nMessaggio > ").strip()
    if not text:
        print("Messaggio vuoto, annullo.")
        return []
    print(f"\nInvio a {len(targets)} destinatari...")
    return send_to_targets(targets, text, on_log=lambda s: print("  " + s))


# ---------------------------------------------------------------------------
# GUI PyQt6 — JARVIS theme (HUD sci-fi)
# ---------------------------------------------------------------------------

# Palette identica a ui.py (class C) per coerenza con la "GUI iniziale".
JARVIS_QSS = """
* { font-family: 'Courier New', 'Consolas', monospace; }
QDialog, QWidget#root {
    background: #00060a;
    color: #8ffcff;
}
QGroupBox {
    border: 1px solid #0d3347;
    border-radius: 4px;
    margin-top: 16px;
    padding: 10px 8px 8px 8px;
    color: #00d4ff;
    background: #010d14;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    color: #00d4ff;
    background: #00060a;
    border: 1px solid #1a5c7a;
    border-radius: 3px;
    font-weight: bold;
    letter-spacing: 1px;
}
QLabel { color: #8ffcff; background: transparent; }
QLabel#title { color: #00d4ff; font-size: 18px; font-weight: bold; letter-spacing: 3px; }
QLabel#subtitle { color: #007a99; font-size: 9px; letter-spacing: 2px; }
QLabel#hdr { color: #00d4ff; font-weight: bold; letter-spacing: 1px; }
QLabel#warn { color: #ff6b00; }
QLabel#ok   { color: #00ff88; }
QLabel#err  { color: #ff3355; }

QCheckBox {
    color: #8ffcff;
    padding: 4px 6px;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px; height: 14px;
    border: 1px solid #1a5c7a;
    background: #00060a;
}
QCheckBox::indicator:checked {
    background: #00d4ff;
    border: 1px solid #00d4ff;
}

QPushButton {
    background: transparent;
    color: #00d4ff;
    border: 1px solid #1a5c7a;
    padding: 6px 14px;
    font-weight: bold;
    letter-spacing: 1px;
    border-radius: 2px;
}
QPushButton:hover {
    background: #001f2e;
    border: 1px solid #00d4ff;
    color: #d8f8ff;
}
QPushButton:pressed { background: #00d4ff; color: #00060a; }
QPushButton:disabled { color: #3a8a9a; border-color: #0d3347; }
QPushButton#primary { color: #00ff88; border-color: #00aa55; }
QPushButton#primary:hover { background: #001a10; border-color: #00ff88; }
QPushButton#danger  { color: #ff6b00; border-color: #ff6b00; }
QPushButton#login   { color: #ffcc00; border-color: #ffcc00; padding: 4px 10px; }
QPushButton#login:hover { background: #1a1400; }

QLineEdit, QTextEdit, QListWidget {
    background: #00060a;
    color: #8ffcff;
    border: 1px solid #0d3347;
    selection-background-color: #001f2e;
    selection-color: #d8f8ff;
    padding: 4px;
}
QLineEdit:focus, QTextEdit:focus, QListWidget:focus {
    border: 1px solid #00d4ff;
}
QLineEdit#search { padding: 6px 10px; font-size: 13px; }

QListWidget::item { padding: 4px 6px; }
QListWidget::item:selected { background: #001f2e; color: #d8f8ff; }
QListWidget::item:hover { background: #010f18; }

QScrollBar:vertical { background: #00060a; width: 10px; }
QScrollBar::handle:vertical { background: #0d3347; min-height: 20px; }
QScrollBar::handle:vertical:hover { background: #1a5c7a; }
QScrollBar::add-line, QScrollBar::sub-line { background: none; border: none; height: 0; }

QSplitter::handle { background: #0d3347; }
"""


def _run_gui_in_this_process(initial_text: str = "") -> int:
    try:
        from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
        from PyQt6.QtGui import QFont
        from PyQt6.QtWidgets import (
            QApplication, QDialog, QVBoxLayout, QHBoxLayout, QCheckBox,
            QPushButton, QLabel, QListWidget, QListWidgetItem, QTextEdit,
            QGroupBox, QSplitter, QLineEdit, QFormLayout, QInputDialog,
            QMessageBox, QFrame, QWidget,
        )
    except Exception as e:
        print(f"[Dashboard] PyQt6 non disponibile: {e}")
        _open_dashboard_cli(initial_text)
        return 0

    app = QApplication.instance() or QApplication(sys.argv)

    # -------- Worker threads --------
    class ScanThread(QThread):
        done = pyqtSignal(str, list, str)
        def __init__(self, platform: str):
            super().__init__(); self.platform = platform
        def run(self):
            try:
                names, diag = SCANNERS[self.platform]()
            except Exception as e:
                names, diag = [], f"Eccezione scanner: {e}"
            self.done.emit(self.platform, names, diag)

    class SendThread(QThread):
        progress = pyqtSignal(str)
        finished_all = pyqtSignal(list)
        def __init__(self, targets, text):
            super().__init__(); self.targets, self.text = targets, text
        def run(self):
            logs = send_to_targets(self.targets, self.text,
                                   on_log=lambda s: self.progress.emit(s))
            self.finished_all.emit(logs)

    # -------- LOGIN DIALOGS --------
    def _styled(dlg):
        dlg.setStyleSheet(JARVIS_QSS); return dlg

    def login_whatsapp():
        ok, msg = _wa_login_start()
        box = QMessageBox(dlg); _styled(box)
        box.setWindowTitle("LOGIN WHATSAPP")
        box.setIcon(QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning)
        box.setText(msg + "\n\nURL bridge: " + WA_BASE)
        box.exec()

    def login_telegram():
        d = QDialog(dlg); _styled(d); d.setWindowTitle("LOGIN TELEGRAM")
        d.resize(420, 0)
        lay = QFormLayout(d)
        e_id   = QLineEdit(os.environ.get("TELEGRAM_API_ID", ""))
        e_hash = QLineEdit(os.environ.get("TELEGRAM_API_HASH", ""))
        e_phone = QLineEdit(); e_phone.setPlaceholderText("+39...")
        lay.addRow(QLabel("API ID"), e_id)
        lay.addRow(QLabel("API HASH"), e_hash)
        lay.addRow(QLabel("Telefono"), e_phone)
        info = QLabel("Riceverai un codice. Inserisci il codice nel popup successivo.")
        info.setObjectName("subtitle"); lay.addRow(info)
        row = QHBoxLayout()
        btn_ok = QPushButton("AUTENTICA"); btn_ok.setObjectName("primary")
        btn_no = QPushButton("Annulla")
        row.addStretch(1); row.addWidget(btn_no); row.addWidget(btn_ok)
        lay.addRow(row)

        def code_provider() -> str:
            text, ok2 = QInputDialog.getText(d, "TELEGRAM", "Codice ricevuto via Telegram:")
            return text.strip() if ok2 else ""
        def pwd_provider() -> str:
            text, ok2 = QInputDialog.getText(d, "TELEGRAM", "Password 2FA Telegram:",
                                             QLineEdit.EchoMode.Password)
            return text.strip() if ok2 else ""

        def do_ok():
            btn_ok.setEnabled(False)
            ok, msg = _tg_login(e_id.text().strip(), e_hash.text().strip(),
                                e_phone.text().strip(), code_provider, pwd_provider)
            box = QMessageBox(d); _styled(box)
            box.setWindowTitle("Telegram")
            box.setIcon(QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning)
            box.setText(msg); box.exec()
            if ok: d.accept()
            else:  btn_ok.setEnabled(True)
        btn_no.clicked.connect(d.reject)
        btn_ok.clicked.connect(do_ok)
        d.exec()

    def login_instagram():
        d = QDialog(dlg); _styled(d); d.setWindowTitle("LOGIN INSTAGRAM")
        d.resize(420, 0)
        lay = QFormLayout(d)
        e_u = QLineEdit()
        e_p = QLineEdit(); e_p.setEchoMode(QLineEdit.EchoMode.Password)
        e_2 = QLineEdit(); e_2.setPlaceholderText("opzionale - solo se 2FA attivo")
        lay.addRow(QLabel("Username"), e_u)
        lay.addRow(QLabel("Password"), e_p)
        lay.addRow(QLabel("Codice 2FA"), e_2)
        info = QLabel("La password NON viene salvata, solo il cookie di sessione.")
        info.setObjectName("subtitle"); lay.addRow(info)
        row = QHBoxLayout()
        btn_ok = QPushButton("ACCEDI"); btn_ok.setObjectName("primary")
        btn_no = QPushButton("Annulla")
        row.addStretch(1); row.addWidget(btn_no); row.addWidget(btn_ok)
        lay.addRow(row)
        def do_ok():
            btn_ok.setEnabled(False)
            ok, msg = _ig_login(e_u.text().strip(), e_p.text(), e_2.text().strip())
            box = QMessageBox(d); _styled(box)
            box.setWindowTitle("Instagram")
            box.setIcon(QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning)
            box.setText(msg); box.exec()
            if ok: d.accept()
            else:  btn_ok.setEnabled(True)
        btn_no.clicked.connect(d.reject)
        btn_ok.clicked.connect(do_ok)
        d.exec()

    def login_discord():
        d = QDialog(dlg); _styled(d); d.setWindowTitle("LOGIN DISCORD")
        d.resize(520, 0)
        lay = QVBoxLayout(d)
        lay.addWidget(QLabel("Incolla il tuo Discord USER token."))
        sub = QLabel("F12 su discord.com -> Network -> qualsiasi richiesta -> header 'Authorization'.\n"
                     "ATTENZIONE: l'uso del self-token viola i ToS Discord. Usalo a tuo rischio.")
        sub.setObjectName("subtitle"); lay.addWidget(sub)
        e_tok = QLineEdit()
        e_tok.setText(os.environ.get("DISCORD_USER_TOKEN", ""))
        e_tok.setEchoMode(QLineEdit.EchoMode.Password)
        lay.addWidget(e_tok)
        row = QHBoxLayout()
        btn_ok = QPushButton("SALVA"); btn_ok.setObjectName("primary")
        btn_no = QPushButton("Annulla")
        row.addStretch(1); row.addWidget(btn_no); row.addWidget(btn_ok)
        lay.addLayout(row)
        def do_ok():
            ok, msg = _dc_save_token(e_tok.text())
            box = QMessageBox(d); _styled(box)
            box.setWindowTitle("Discord")
            box.setIcon(QMessageBox.Icon.Information if ok else QMessageBox.Icon.Warning)
            box.setText(msg); box.exec()
            if ok: d.accept()
        btn_no.clicked.connect(d.reject)
        btn_ok.clicked.connect(do_ok)
        d.exec()

    LOGIN_FNS = {
        "whatsapp":  login_whatsapp,
        "telegram":  login_telegram,
        "discord":   login_discord,
        "instagram": login_instagram,
    }

    # -------- MAIN WINDOW --------
    dlg = QDialog(None)
    dlg.setObjectName("root")
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
    dlg.setWindowTitle("J.A.R.V.I.S. // UNIFIED MESSAGING")
    dlg.resize(1100, 720)
    dlg.setStyleSheet(JARVIS_QSS)

    root = QVBoxLayout(dlg)
    root.setContentsMargins(18, 14, 18, 14)
    root.setSpacing(10)

    # ---- header ----
    head = QHBoxLayout()
    title = QLabel("J.A.R.V.I.S.  >  UNIFIED  MESSAGING"); title.setObjectName("title")
    sub   = QLabel("CROSS-PLATFORM // TOKEN-ONLY // NO BROWSER")
    sub.setObjectName("subtitle")
    head_l = QVBoxLayout(); head_l.addWidget(title); head_l.addWidget(sub)
    head.addLayout(head_l); head.addStretch(1)
    status_lbl = QLabel("> SYSTEM ONLINE")
    status_lbl.setObjectName("ok")
    head.addWidget(status_lbl)
    root.addLayout(head)

    # ---- piattaforme + login ----
    plat_box = QGroupBox("[ 01 ]  PIATTAFORME  /  LOGIN")
    plat_lay = QHBoxLayout(plat_box); plat_lay.setSpacing(14)
    plat_checks: dict[str, QCheckBox] = {}
    for p in PLATFORMS:
        col = QVBoxLayout(); col.setSpacing(4)
        cb = QCheckBox(PLATFORM_LABEL[p].upper())
        plat_checks[p] = cb
        col.addWidget(cb)
        b = QPushButton("LOGIN " + PLATFORM_LABEL[p][:2].upper())
        b.setObjectName("login")
        b.clicked.connect(lambda _=False, plat=p: LOGIN_FNS[plat]())
        col.addWidget(b)
        wrap = QWidget(); wrap.setLayout(col)
        plat_lay.addWidget(wrap)
    plat_lay.addStretch(1)
    # ---- indicatore live stato bridge WhatsApp ----
    wa_status_lbl = QLabel("WA: ...")
    wa_status_lbl.setObjectName("hdr")
    wa_status_lbl.setStyleSheet("color:#ffcc00; padding: 0 8px;")
    plat_lay.addWidget(wa_status_lbl)
    btn_scan = QPushButton("> SCANSIONA CHAT"); btn_scan.setObjectName("primary")
    plat_lay.addWidget(btn_scan)
    root.addWidget(plat_box)

    # ---- WhatsApp ACTIONS (vocale + chiamata) ----
    wa_actions = QGroupBox("[ WA ]  AZIONI WHATSAPP")
    wa_lay = QHBoxLayout(wa_actions)
    wa_target = QLineEdit()
    wa_target.setPlaceholderText("destinatario WhatsApp (nome contatto o +39...)")
    btn_rec_start = QPushButton("REC vocale"); btn_rec_start.setObjectName("primary")
    btn_rec_stop  = QPushButton("STOP & INVIA"); btn_rec_stop.setEnabled(False)
    btn_call_wa   = QPushButton("CHIAMA")
    wa_lay.addWidget(wa_target, 1)
    wa_lay.addWidget(btn_rec_start)
    wa_lay.addWidget(btn_rec_stop)
    wa_lay.addWidget(btn_call_wa)
    root.addWidget(wa_actions)

    _wa_rec_path = {"wav": None}

    def _do_rec_start():
        try:
            from actions.voice_io import start_recording
            ok, msg = start_recording()
        except Exception as e:
            ok, msg = False, f"voice_io non disponibile: {e}"
        if ok:
            btn_rec_start.setEnabled(False)
            btn_rec_stop.setEnabled(True)
            log_view.append("[WA-VOICE] " + msg)
        else:
            log_view.append("[WA-VOICE] " + msg)

    def _do_rec_stop_and_send():
        try:
            from actions.voice_io import stop_recording_and_save_wav, send_recorded_voice_whatsapp
        except Exception as e:
            log_view.append(f"[WA-VOICE] modulo non disponibile: {e}"); return
        btn_rec_stop.setEnabled(False)
        wav = stop_recording_and_save_wav()
        if not wav:
            log_view.append("[WA-VOICE] registrazione vuota.")
            btn_rec_start.setEnabled(True); return
        recipient = wa_target.text().strip()
        if not recipient:
            log_view.append("[WA-VOICE] destinatario mancante.")
            btn_rec_start.setEnabled(True); return
        ok, info = send_recorded_voice_whatsapp(recipient, wav)
        log_view.append(("[WA-VOICE] inviato a " + recipient) if ok
                         else ("[WA-VOICE] errore: " + info[:120]))
        btn_rec_start.setEnabled(True)

    def _do_call_wa():
        try:
            from actions.calls import start_call
        except Exception as e:
            log_view.append(f"[WA-CALL] modulo non disponibile: {e}"); return
        recipient = wa_target.text().strip()
        if not recipient:
            log_view.append("[WA-CALL] destinatario mancante."); return
        out = start_call({"platform": "whatsapp", "receiver": recipient})
        log_view.append("[WA-CALL] " + out)

    btn_rec_start.clicked.connect(_do_rec_start)
    btn_rec_stop.clicked.connect(_do_rec_stop_and_send)
    btn_call_wa.clicked.connect(_do_call_wa)

    def _refresh_wa_status():
        st = _wa_status()
        if not st["online"]:
            wa_status_lbl.setText("WA: BRIDGE OFFLINE")
            wa_status_lbl.setStyleSheet("color:#ff3355;")
        elif not st["ready"]:
            wa_status_lbl.setText("WA: scansiona QR")
            wa_status_lbl.setStyleSheet("color:#ffcc00;")
        else:
            wa_status_lbl.setText("WA: CONNESSO")
            wa_status_lbl.setStyleSheet("color:#00ff88;")
    _wa_timer = QTimer(dlg)
    _wa_timer.timeout.connect(_refresh_wa_status)
    _wa_timer.start(4000)
    QTimer.singleShot(300, _refresh_wa_status)

    # ---- search bar ----
    search_row = QHBoxLayout()
    s_lbl = QLabel("[ FILTER ]"); s_lbl.setObjectName("hdr")
    search = QLineEdit(); search.setObjectName("search")
    search.setPlaceholderText("Cerca chat: scrivi qui per filtrare tutte le piattaforme...")
    search_row.addWidget(s_lbl); search_row.addWidget(search, 1)
    btn_clear = QPushButton("CLEAR"); search_row.addWidget(btn_clear)
    root.addLayout(search_row)

    # ---- splitter destinatari / messaggio ----
    split = QSplitter(Qt.Orientation.Horizontal)
    root.addWidget(split, 1)

    lists_box = QGroupBox("[ 02 ]  DESTINATARI  (selezione multipla)")
    lists_lay = QVBoxLayout(lists_box)
    chats_lists: dict[str, QListWidget] = {}
    labels_map: dict[str, QLabel] = {}
    for p in PLATFORMS:
        lbl = QLabel("> " + PLATFORM_LABEL[p].upper() + "  - nessuna scansione")
        lbl.setObjectName("hdr")
        lw = QListWidget()
        lw.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        lw.setVisible(False); lbl.setVisible(False)
        chats_lists[p] = lw; labels_map[p] = lbl
        lists_lay.addWidget(lbl); lists_lay.addWidget(lw)
    lists_lay.addStretch(1)
    split.addWidget(lists_box)

    msg_box = QGroupBox("[ 03 ]  MESSAGGIO")
    msg_lay = QVBoxLayout(msg_box)
    msg_edit = QTextEdit()
    msg_edit.setPlainText(initial_text)
    msg_edit.setPlaceholderText("Scrivi qui il messaggio per TUTTI i destinatari selezionati...")
    msg_lay.addWidget(msg_edit, 1)
    log_view = QTextEdit(); log_view.setReadOnly(True); log_view.setMaximumHeight(180)
    log_view.setPlaceholderText("> LOG_INVIO //")
    msg_lay.addWidget(log_view)
    btn_row = QHBoxLayout()
    btn_send = QPushButton(">> TRASMETTI <<"); btn_send.setObjectName("primary")
    btn_cancel = QPushButton("CHIUDI"); btn_cancel.setObjectName("danger")
    btn_row.addStretch(1); btn_row.addWidget(btn_cancel); btn_row.addWidget(btn_send)
    msg_lay.addLayout(btn_row)
    split.addWidget(msg_box)
    split.setSizes([520, 580])

    dlg._threads: list[Any] = []

    # ---- filtro live ----
    def apply_filter():
        q = search.text().strip().lower()
        for p in PLATFORMS:
            lst = chats_lists[p]
            visible = 0
            total = lst.count()
            for i in range(total):
                it = lst.item(i)
                show = (q in it.text().lower()) if q else True
                it.setHidden(not show)
                if show: visible += 1
            if lst.isVisible():
                if q:
                    labels_map[p].setText(f"> {PLATFORM_LABEL[p].upper()} - {visible}/{total} (filtrate)")
                else:
                    labels_map[p].setText(f"> {PLATFORM_LABEL[p].upper()} - {total} chat")
    search.textChanged.connect(lambda _t: apply_filter())
    btn_clear.clicked.connect(lambda: search.setText(""))

    # ---- scan ----
    def on_scan():
        wanted = [p for p, cb in plat_checks.items() if cb.isChecked()]
        if not wanted:
            log_view.append("[!] Seleziona almeno una piattaforma."); return
        btn_scan.setEnabled(False)
        log_view.append("> SCAN: " + ", ".join(PLATFORM_LABEL[p] for p in wanted) + "...")
        remaining = [len(wanted)]
        for p in wanted:
            labels_map[p].setText(f"> {PLATFORM_LABEL[p].upper()} - scansione in corso...")
            labels_map[p].setVisible(True)
            chats_lists[p].setVisible(True)
            chats_lists[p].clear()
            _ID_MAP[p].clear()
            t = ScanThread(p)
            def _done(plat_id, names, diag):
                lst = chats_lists[plat_id]
                lblw = labels_map[plat_id]
                log_view.append(f"[{PLATFORM_LABEL[plat_id]}] {diag}")
                if not names:
                    lblw.setText(f"> {PLATFORM_LABEL[plat_id].upper()} - 0 chat // {diag}")
                    lblw.setObjectName("warn")
                    lblw.setStyleSheet("color:#ff6b00;")
                else:
                    lblw.setText(f"> {PLATFORM_LABEL[plat_id].upper()} - {len(names)} chat")
                    lblw.setObjectName("hdr")
                    lblw.setStyleSheet("color:#00d4ff;")
                    for n in names:
                        QListWidgetItem(n, lst)
                remaining[0] -= 1
                if remaining[0] <= 0:
                    btn_scan.setEnabled(True)
                    apply_filter()
            t.done.connect(_done); t.start()
            dlg._threads.append(t)

    # ---- send ----
    def on_send():
        text = msg_edit.toPlainText().strip()
        if not text:
            log_view.append("[!] Inserisci il testo del messaggio."); return
        targets: list[tuple[str, str]] = []
        for p, lw in chats_lists.items():
            for it in lw.selectedItems():
                targets.append((p, it.text()))
        if not targets:
            log_view.append("[!] Seleziona almeno un destinatario."); return
        btn_send.setEnabled(False)
        log_view.append(f"> TRANSMIT to {len(targets)} target(s)...")
        st = SendThread(targets, text)
        st.progress.connect(lambda s: log_view.append("  " + s))
        def _fin(_logs):
            log_view.append("--- FATTO ---")
            btn_send.setEnabled(True)
        st.finished_all.connect(_fin)
        st.start(); dlg._threads.append(st)

    btn_scan.clicked.connect(on_scan)
    btn_send.clicked.connect(on_send)
    btn_cancel.clicked.connect(dlg.close)

    dlg.show(); dlg.raise_(); dlg.activateWindow()
    return app.exec()


# ---------------------------------------------------------------------------
# Entry point pubblico
# ---------------------------------------------------------------------------

def open_dashboard(initial_text: str = "", prefer_gui: bool = True) -> None:
    env = dict(os.environ)
    env["JARVIS_DASHBOARD_INITIAL_TEXT"] = initial_text or ""
    env["JARVIS_DASHBOARD_PREFER_GUI"]   = "1" if prefer_gui else "0"
    project_root = Path(__file__).resolve().parent.parent
    try:
        kwargs: dict[str, Any] = {}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = 0x00000008 | 0x00000200
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(
            [sys.executable, "-m", "actions.send_dashboard"],
            cwd=str(project_root), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            **kwargs,
        )
    except Exception as e:
        print(f"[Dashboard] subprocess fallito ({e}), fallback CLI in thread.")
        threading.Thread(target=lambda: _open_dashboard_cli(initial_text), daemon=True).start()


def _main_entry() -> int:
    initial = os.environ.get("JARVIS_DASHBOARD_INITIAL_TEXT", "")
    prefer_gui = os.environ.get("JARVIS_DASHBOARD_PREFER_GUI", "1") == "1"
    if not prefer_gui:
        _open_dashboard_cli(initial); return 0
    try:
        return _run_gui_in_this_process(initial)
    except Exception as e:
        print(f"[Dashboard] errore GUI: {e}")
        _open_dashboard_cli(initial); return 0


if __name__ == "__main__":
    sys.exit(_main_entry())

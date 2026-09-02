import os
import re
import time
import base64
import ctypes
import difflib
import logging
import subprocess
import unicodedata
from ctypes import wintypes
from pathlib import Path
from urllib.parse import unquote, urlparse, parse_qs, quote_plus

import requests

log = logging.getLogger(__name__)
if not log.handlers:
    logging.basicConfig(
        level=os.environ.get("SPOTIFY_LOG_LEVEL", "INFO"),
        format="[spotify] %(levelname)s %(message)s",
    )
log.setLevel(os.environ.get("SPOTIFY_LOG_LEVEL", "INFO"))

# ------------------------------------------------------------------
# COSTANTI WINDOWS
# ------------------------------------------------------------------
WM_APPCOMMAND = 0x0319
APPCOMMAND_MEDIA_PLAY = 46
APPCOMMAND_MEDIA_PAUSE = 47
APPCOMMAND_MEDIA_PLAY_PAUSE = 14
APPCOMMAND_MEDIA_NEXTTRACK = 11
APPCOMMAND_MEDIA_PREVIOUSTRACK = 12

SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_SHOWNOACTIVATE = 4
SW_MINIMIZE = 6
SW_SHOWNA = 8
SW_FORCEMINIMIZE = 11

_UA_BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_TRACK_ID_RE = re.compile(
    r"(?:https?://)?(?:open|embed)\.spotify\.com/"
    r"(?:intl-[a-z]{2}/)?(?:embed/)?track/([A-Za-z0-9]{22})"
    r"(?:[/?#&][^\s<>'\"\)]*)?",
    re.IGNORECASE,
)
_SPOTIFY_URI_RE = re.compile(
    r"spotify:(?:track:)?([A-Za-z0-9]{22})(?=$|[\s<>'\"&?#])",
    re.IGNORECASE,
)
_B64_PARAM_RE = re.compile(r"(?:[?&](?:u|url|target)=)([^&\s<>\"']+)", re.IGNORECASE)

# ------------------------------------------------------------------
# CREDENZIALI (Client Credentials Flow)
# ------------------------------------------------------------------
_APP_TOKEN_CACHE = {"token": None, "expires_at": 0}
_CREDS_FILE_NAMES = ["spotify_credentials.txt", ".spotify_credentials"]
_API_BLOCKED_PREMIUM = False


def _load_credentials():
    cid = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    csec = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
    if cid and csec:
        return cid, csec

    search_dirs = [Path(__file__).resolve().parent, Path.cwd()]
    for d in search_dirs:
        for name in _CREDS_FILE_NAMES:
            p = d / name
            if not p.exists():
                continue
            try:
                content = p.read_text(encoding="utf-8")
            except Exception:
                continue
            pairs = {}
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    pairs[k.strip().lower()] = v.strip().strip('"').strip("'")
            cid = pairs.get("client_id") or pairs.get("spotify_client_id")
            csec = pairs.get("client_secret") or pairs.get("spotify_client_secret")
            if cid and csec:
                return cid, csec
    return None, None


def _short_body(r):
    try:
        t = r.text
    except Exception:
        return ""
    if not t:
        return ""
    t = t.replace("\n", " ").strip()
    return t[:300] + ("…" if len(t) > 300 else "")


def _get_app_token(force_refresh=False):
    now = time.time()
    if (not force_refresh
            and _APP_TOKEN_CACHE["token"]
            and now < _APP_TOKEN_CACHE["expires_at"] - 60):
        return _APP_TOKEN_CACHE["token"]

    cid, csec = _load_credentials()
    if not cid or not csec:
        log.warning("Nessuna credenziale Spotify trovata.")
        return None

    try:
        auth = base64.b64encode(f"{cid}:{csec}".encode("utf-8")).decode("ascii")
        r = requests.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"},
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=10,
        )
        if r.status_code != 200:
            log.error("Token POST HTTP %s - body: %s", r.status_code, _short_body(r))
            return None
        data = r.json()
        token = data.get("access_token")
        if not token:
            return None
        _APP_TOKEN_CACHE["token"] = token
        _APP_TOKEN_CACHE["expires_at"] = now + int(data.get("expires_in", 3500))
        log.info("Token App OK (expires_in=%ss)", data.get("expires_in"))
        return token
    except Exception as e:
        log.exception("Eccezione durante richiesta token: %s", e)
        return None


def has_credentials():
    cid, csec = _load_credentials()
    return bool(cid and csec)


# ------------------------------------------------------------------
# LEGACY anon token (fallback) + persistent web-player session
# ------------------------------------------------------------------
_TOKEN_CACHE = {"token": None, "expires_at": 0}
_CLIENT_TOKEN_CACHE = {"token": None, "expires_at": 0}
_ANON_SESSION = None


def _get_anon_session():
    """Ritorna una requests.Session persistente con i cookie di open.spotify.com.
    Serve sia per prendere l'anon token sia per le successive chiamate Partner API
    e per lo scraping HTML autenticato.
    """
    global _ANON_SESSION
    if _ANON_SESSION is not None:
        return _ANON_SESSION
    s = requests.Session()
    s.headers.update({
        "User-Agent": _UA_BROWSER,
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    })
    try:
        s.get("https://open.spotify.com/", timeout=10)
    except Exception:
        pass
    _ANON_SESSION = s
    return s


def _get_anon_token():
    """Ottiene un token anonimo del web player.

    Usa una requests.Session persistente e prova due endpoint:
      1. https://open.spotify.com/api/token  (endpoint moderno, 2024+)
      2. https://open.spotify.com/get_access_token  (legacy, ancora attivo su alcuni tenant)

    Ritorna il token stringa oppure None.
    """
    now = time.time()
    if _TOKEN_CACHE["token"] and now < _TOKEN_CACHE["expires_at"] - 60:
        return _TOKEN_CACHE["token"]

    s = _get_anon_session()
    headers = {
        "Accept": "application/json",
        "App-Platform": "WebPlayer",
        "Spotify-App-Version": "1.2.52.313",
        "Referer": "https://open.spotify.com/",
        "Origin": "https://open.spotify.com",
    }

    # Tentativo 1: endpoint moderno /api/token
    for endpoint, params in (
        ("https://open.spotify.com/api/token",
         {"reason": "init", "productType": "web-player"}),
        ("https://open.spotify.com/get_access_token",
         {"reason": "transport", "productType": "web_player"}),
    ):
        try:
            r = s.get(endpoint, params=params, headers=headers, timeout=10)
            if r.status_code != 200:
                log.debug("anon token endpoint %s HTTP %s", endpoint, r.status_code)
                continue
            data = r.json()
            token = data.get("accessToken") or data.get("access_token")
            if not token:
                continue
            _TOKEN_CACHE["token"] = token
            exp_ms = data.get("accessTokenExpirationTimestampMs") or 0
            _TOKEN_CACHE["expires_at"] = (
                (exp_ms / 1000.0) if exp_ms else (now + 3000)
            )
            log.info("Anon token OK (%s, len=%d)", endpoint.rsplit("/", 1)[-1], len(token))
            return token
        except Exception as e:
            log.debug("anon token endpoint %s exception: %s", endpoint, e)
            continue

    return None


def _get_client_token():
    """Ottiene il client-token opzionale usato dalle chiamate Partner API.

    Alcune route Partner richiedono l'header 'client-token' oltre al Bearer anon.
    L'endpoint accetta un client_data JSON con client_id del web player.
    Ritorna la stringa token oppure None se non disponibile.
    """
    now = time.time()
    if _CLIENT_TOKEN_CACHE["token"] and now < _CLIENT_TOKEN_CACHE["expires_at"] - 60:
        return _CLIENT_TOKEN_CACHE["token"]

    s = _get_anon_session()
    payload = {
        "client_data": {
            "client_version": "1.2.52.313.gec1b3d2f",
            "client_id": "d8a5ed958d274c2e8ee717e6a4b0971d",
            "js_sdk_data": {
                "device_brand": "unknown",
                "device_model": "unknown",
                "os": "windows",
                "os_version": "NT 10.0",
                "device_id": "web-player",
                "device_type": "computer",
            },
        }
    }
    try:
        r = s.post(
            "https://clienttoken.spotify.com/v1/clienttoken",
            json=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Origin": "https://open.spotify.com",
                "Referer": "https://open.spotify.com/",
            },
            timeout=10,
        )
        if r.status_code != 200:
            log.debug("client-token HTTP %s", r.status_code)
            return None
        data = r.json()
        gc = data.get("granted_token") or {}
        token = gc.get("token")
        if not token:
            return None
        _CLIENT_TOKEN_CACHE["token"] = token
        _CLIENT_TOKEN_CACHE["expires_at"] = now + int(gc.get("expires_after_seconds", 1200))
        log.info("Client token OK (len=%d)", len(token))
        return token
    except Exception as e:
        log.debug("client-token exception: %s", e)
        return None


def _track_dict(t):
    """Helper: normalizza un track dict Spotify in un dict interno compatto.
    Usa .get() ovunque, così funziona sia con /v1/search sia con Partner API.
    """
    if not t:
        return None
    artists = t.get("artists") or []
    if artists and isinstance(artists[0], dict):
        artist_names = [a.get("name") or "" for a in artists if a.get("name")]
    else:
        artist_names = [str(a) for a in artists if a]
    tid = t.get("id") or ""
    uri = t.get("uri") or (f"spotify:track:{tid}" if tid else "")
    return {
        "uri": uri,
        "id": tid,
        "name": t.get("name") or "",
        "artist": ", ".join(artist_names),
        "popularity": t.get("popularity", 0) or 0,
    }


# ------------------------------------------------------------------
# PARTNER API (GraphQL Pathfinder) - funziona con app OWNER FREE
# ------------------------------------------------------------------
_PARTNER_URL = "https://api-partner.spotify.com/pathfinder/v1/query"
# Hash pubblici usati dal web player Spotify (searchDesktop / searchTracks)
_PARTNER_SEARCH_HASH = "4bd9f2d8cedad57036f7c9ab00d0d5b7c6f7ef4d0e0a7c0d0e0a7c0d0e0a7c0d"
_PARTNER_SEARCH_HASH_V2 = (
    "b8f5c8f2c8b0e5a7d3f5c8b0e5a7d3f5c8b0e5a7d3f5c8b0e5a7d3f5c8b0e5a7"
)


def _search_via_partner_api(song, limit=10):
    """Ricerca via GraphQL Pathfinder. Funziona anche se l'app OWNER è FREE
    perché usa l'access token del web player anonimo (utente-based) e NON
    l'app token client-credentials.

    Prova varianti progressive della query (query pulita, senza qualificatori
    di versione, solo titolo, ecc.) per migliorare il recall su query
    come "poetica di cremonini" o "ex angelo versione originale di kid yugi".

    Ritorna un track dict normalizzato oppure None.
    """
    global _API_BLOCKED_PREMIUM
    token = _get_anon_token()
    if not token:
        return None

    def _do_partner_request(q_term: str):
        variables = {
            "searchTerm": q_term,
            "offset": 0,
            "limit": limit,
            "numberOfTopResults": 5,
            "includeAudiobooks": False,
            "includePreReleases": False,
        }
        inline_query = """
        query searchDesktop($searchTerm: String!, $offset: Int!, $limit: Int!) {
          searchV2(searchTerm: $searchTerm, offset: $offset, limit: $limit,
                   numberOfTopResults: 5, includeAudiobooks: false) {
            tracksV2 {
              items {
                item {
                  data {
                    __typename
                    uri
                    id
                    name
                    artists { items { profile { name } } }
                  }
                }
              }
            }
          }
        }
        """
        payload = {
            "operationName": "searchDesktop",
            "variables": variables,
            "query": inline_query,
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "App-Platform": "WebPlayer",
            "Spotify-App-Version": "1.2.52.313",
            "Origin": "https://open.spotify.com",
            "Referer": "https://open.spotify.com/",
        }
        ctok = _get_client_token()
        if ctok:
            headers["client-token"] = ctok

        s = _get_anon_session()
        try:
            r = s.post(_PARTNER_URL, json=payload, headers=headers, timeout=12)
        except Exception as e:
            log.debug("Partner API exception: %s", e)
            return []
        if r.status_code != 200:
            log.debug("Partner API HTTP %s - %s", r.status_code, _short_body(r))
            return []
        try:
            data = r.json()
        except Exception:
            return []
        try:
            items_raw = (((data.get("data") or {})
                          .get("searchV2") or {})
                         .get("tracksV2") or {}).get("items") or []
        except Exception:
            items_raw = []
        out = []
        for it in items_raw:
            d = ((it or {}).get("item") or {}).get("data") or {}
            if not d.get("id") and not d.get("uri"):
                continue
            artists = []
            for a in (((d.get("artists") or {}).get("items")) or []):
                name = ((a or {}).get("profile") or {}).get("name")
                if name:
                    artists.append({"name": name})
            tid = d.get("id") or ""
            uri = d.get("uri") or (f"spotify:track:{tid}" if tid else "")
            if not tid and uri.startswith("spotify:track:"):
                tid = uri.split(":")[-1]
            out.append({
                "id": tid,
                "uri": uri,
                "name": d.get("name") or "",
                "artists": artists,
                "popularity": 0,
            })
        return out

    variants = _build_query_variants(song)
    # partner API non capisce i field-filter tipo track:"..." — filtriamoli
    variants = [v for v in variants if 'track:"' not in v and 'artist:"' not in v]
    if not variants:
        variants = [song]

    best_overall = None
    best_overall_score = -1.0
    for idx, q in enumerate(variants):
        log.info("Partner-API variant %d/%d: %r", idx + 1, len(variants), q)
        tracks = _do_partner_request(q)
        if not tracks:
            continue
        best = _pick_best_match(tracks, song) or tracks[0]
        title_guess, _ = _try_split_song_artist(_strip_version_qualifiers(song))
        qt = _normalize(_strip_version_qualifiers(title_guess or song))
        name_clean = _normalize(_strip_version_qualifiers(best.get("name", "")))
        quality = max(
            _name_similarity(qt, name_clean),
            _token_overlap(qt, name_clean),
        )
        if quality > best_overall_score:
            best_overall_score = quality
            best_overall = best
        if quality >= 0.85:
            break

    if not best_overall:
        return None
    # Partner API funziona anche se l'app è FREE: sblocchiamo esplicitamente
    # eventuali flag di premium-block segnalati da /v1/search.
    if _API_BLOCKED_PREMIUM:
        log.info("Partner API OK: bypasso il blocco premium di /v1/search")
    return _track_dict(best_overall)


# ------------------------------------------------------------------
# STRING NORMALIZATION + MATCHING
# ------------------------------------------------------------------
def _normalize(s: str) -> str:
    """Toglie accenti, lowercase, comprime spazi/punteggiatura."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# Stopwords / filler che vanno tolti dalla query per il matching titolo
_FILLER_WORDS = {
    "di", "del", "della", "dei", "delle", "da", "dal", "il", "la", "lo",
    "le", "gli", "i", "un", "una", "uno", "by", "of", "the",
    "feat", "ft", "featuring", "con", "and",
}

# Qualificatori di versione che l'utente aggiunge per disambiguare, ma che
# spesso NON compaiono nel nome ufficiale della traccia su Spotify.
# Es. "ex angelo versione originale di kid yugi" -> Spotify ha solo "Ex-Angelo".
_VERSION_QUALIFIERS = [
    "versione originale", "versione originali", "versione ufficiale",
    "versione italiana", "versione inglese", "versione album",
    "versione studio", "versione singolo", "versione estesa",
    "versione radio", "versione acustica",
    "original version", "album version", "studio version",
    "single version", "extended version", "radio edit", "radio version",
    "official version", "official audio", "official video",
    "originale", "ufficiale",
]
# Ordina per lunghezza discendente per matching greedy
_VERSION_QUALIFIERS_SORTED = sorted(_VERSION_QUALIFIERS, key=len, reverse=True)


def _strip_filler(text: str) -> str:
    toks = [t for t in _normalize(text).split() if t not in _FILLER_WORDS]
    return " ".join(toks)


def _strip_version_qualifiers(text: str) -> str:
    """Rimuove qualificatori di versione ("versione originale", "original
    version", "radio edit", ...) dal testo, sia dalla query che dai nomi
    di traccia. Ritorna il testo pulito (mantiene case e punteggiatura
    per la query Spotify)."""
    if not text:
        return text
    out = text
    # Match sui qualificatori (case-insensitive) preceduti/seguiti da
    # separatori (spazi, trattini, virgole, parentesi).
    for q in _VERSION_QUALIFIERS_SORTED:
        pat = r"(?i)(?:[\s\-,()\[\]]|^)" + re.escape(q) + r"(?=[\s\-,()\[\]]|$)"
        out = re.sub(pat, " ", out)
    out = re.sub(r"\s+", " ", out).strip(" -,")
    return out


def _tokens(text: str) -> set:
    """Insieme di token normalizzati (senza filler)."""
    return {t for t in _normalize(text).split() if t and t not in _FILLER_WORDS}


def _token_overlap(a: str, b: str) -> float:
    """Jaccard-like overlap tra i token di due stringhe."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    union = ta | tb
    return len(inter) / len(union)


def _try_split_song_artist(query: str):
    """Se la query è 'titolo artista' o 'titolo di artista', prova a separare.
    Ritorna (titolo_guess, artista_guess_or_None).
    Supporta: "titolo di X", "titolo by X", "titolo of X",
              "titolo - X", "X - titolo", "titolo, X", "titolo (X)"
    """
    q = query.strip()
    # pattern: " di <artista>" / " by <artista>" / " of <artista>"
    m = re.search(r"\s+(?:di|by|of)\s+(.+)$", q, flags=re.IGNORECASE)
    if m:
        artist = m.group(1).strip(" -,()[]")
        title = q[:m.start()].strip(" -,()[]")
        if title and artist:
            return title, artist
    # pattern: "titolo - artista" o "artista - titolo" (ambiguo,
    # proviamo "titolo - artista" perche' e' l'ordine piu' comune quando
    # l'utente scrive).
    if " - " in q:
        left, right = [s.strip(" -,()[]") for s in q.split(" - ", 1)]
        if left and right:
            return left, right
    # pattern: "titolo (artista)" o "titolo [artista]"
    m = re.search(r"^(.+?)\s*[\(\[]([^\)\]]+)[\)\]]\s*$", q)
    if m:
        title = m.group(1).strip()
        artist = m.group(2).strip()
        if title and artist:
            return title, artist
    return q, None


def _progressive_splits(query: str) -> list:
    """Genera split alternativi (titolo, artista) senza separatori espliciti.
    Utile per query come 'Alaska Baby Cesare Cremonini' dove utente
    concatena titolo e artista senza 'di/-/(...)'.

    Prova a rompere la query in tutti i punti possibili, favorendo le
    combinazioni dove l'artista occupa 1-3 token finali.
    """
    q = (query or "").strip()
    if not q:
        return []
    toks = [t for t in re.split(r"\s+", q) if t]
    if len(toks) < 2:
        return []

    seen: set = set()
    out: list = []
    # Preferisci nomi artista da 2 token (più comune), poi 3, poi 1
    for n_artist in (2, 3, 1, 4):
        if n_artist >= len(toks):
            continue
        title = " ".join(toks[:-n_artist]).strip()
        artist = " ".join(toks[-n_artist:]).strip()
        if not title or not artist:
            continue
        key = (title.lower(), artist.lower())
        if key in seen:
            continue
        seen.add(key)
        out.append((title, artist))
    return out


def _name_similarity(query_norm: str, track_name_norm: str) -> float:
    if not query_norm or not track_name_norm:
        return 0.0
    return difflib.SequenceMatcher(None, query_norm, track_name_norm).ratio()


def _artist_match(query_artist_norm: str, track_artists_norm: str) -> float:
    if not query_artist_norm or not track_artists_norm:
        return 0.0
    if query_artist_norm in track_artists_norm:
        return 1.0
    return difflib.SequenceMatcher(None, query_artist_norm, track_artists_norm).ratio()


def _pick_best_match(items: list, original_query: str):
    """Sceglie la traccia migliore tra i risultati Spotify.

    Algoritmo:
    1. Se la query contiene "titolo di artista" → filtra per quell'artista.
    2. Score = bonus_match_esatto + bonus_contiene + similarity_nome + popolarità.
       In pratica: prima viene la somiglianza del NOME, poi la popolarità.
    """
    if not items:
        return None

    title_guess, artist_guess = _try_split_song_artist(original_query)
    # Rimuovi qualificatori di versione dal titolo prima di matchare
    # (l'utente scrive "ex angelo versione originale" ma su Spotify e' solo
    # "Ex-Angelo").
    title_guess_clean = _strip_version_qualifiers(title_guess)
    qt = _normalize(title_guess_clean or title_guess)
    qt_stripped = _strip_filler(title_guess_clean or title_guess)
    qa = _normalize(artist_guess) if artist_guess else None

    # Filtra per artista se specificato (soft filter: se nessuno matcha, non filtrare)
    candidates = items
    artist_filter_applied = False
    if qa:
        filtered = []
        for t in items:
            artists_norm = _normalize(", ".join(a["name"] for a in t.get("artists", [])))
            if qa and (qa in artists_norm or artists_norm in qa
                       or _artist_match(qa, artists_norm) >= 0.7):
                filtered.append(t)
        if filtered:
            candidates = filtered
            artist_filter_applied = True

    best = None
    best_score = -1.0
    for t in candidates:
        raw_name = t.get("name", "")
        # Anche il nome della traccia puo' contenere "- Remastered" etc.:
        # per il matching consideriamo entrambe le forme.
        name_norm = _normalize(raw_name)
        name_clean_norm = _normalize(_strip_version_qualifiers(raw_name))
        name_stripped = _strip_filler(raw_name)
        name_clean_stripped = _strip_filler(_strip_version_qualifiers(raw_name))
        artists_norm = _normalize(", ".join(a["name"] for a in t.get("artists", [])))
        popularity = float(t.get("popularity", 0))  # 0-100

        sim_full = max(_name_similarity(qt, name_norm),
                       _name_similarity(qt, name_clean_norm))
        sim_stripped = max(_name_similarity(qt_stripped, name_stripped),
                           _name_similarity(qt_stripped, name_clean_stripped))
        # Token-overlap: piu' robusto contro riordinamenti e parole extra
        sim_tokens = max(_token_overlap(qt, name_norm),
                         _token_overlap(qt, name_clean_norm))
        sim = max(sim_full, sim_stripped, sim_tokens)

        exact_bonus = 0.0
        if (qt and (qt == name_norm or qt == name_clean_norm
                    or qt_stripped == name_stripped
                    or qt_stripped == name_clean_stripped)):
            exact_bonus = 200.0
        contains_bonus = 0.0
        if qt and (qt in name_norm or name_norm in qt
                   or qt in name_clean_norm or name_clean_norm in qt):
            contains_bonus = 60.0
        artist_bonus = 0.0
        if qa:
            am = _artist_match(qa, artists_norm)
            artist_bonus = am * 80.0
            # Penalizza pesantemente i risultati che NON matchano l'artista
            # richiesto, così tracce popolari con titolo simile ma artista
            # diverso non vincono per pura popolarità.
            if not artist_filter_applied and am < 0.5:
                artist_bonus -= 120.0

        # Penalità per remix/edit/sped up se la query non li chiedeva
        penalty = 0.0
        suspicious = ("remix", "sped up", "slowed", "remaster", "live",
                      "acoustic", "instrumental", "karaoke", "cover")
        qfull = _normalize(original_query)
        for word in suspicious:
            if word in name_norm and word not in qfull:
                penalty += 25.0
                break

        # Composizione finale: la somiglianza del nome pesa molto (×150),
        # poi popolarità (×1, range 0-100), poi bonus.
        score = (sim * 150.0) + exact_bonus + contains_bonus + artist_bonus + popularity - penalty

        log.debug("  candidate=%r artist=%r pop=%.0f sim=%.2f score=%.1f",
                  t.get("name"), ", ".join(a["name"] for a in t.get("artists", [])),
                  popularity, sim, score)

        if score > best_score:
            best_score = score
            best = t

    if best:
        log.info("Best match: %r - %r (pop=%s, score=%.1f)",
                 best.get("name"),
                 ", ".join(a["name"] for a in best.get("artists", [])),
                 best.get("popularity"), best_score)
    return best


# ------------------------------------------------------------------
# /v1/search
# ------------------------------------------------------------------
def _do_search_request(token, song, market=None, limit=10):
    """Ritorna (items, status_code, body_snippet)."""
    global _API_BLOCKED_PREMIUM
    params = {"q": song, "type": "track", "limit": limit}
    if market:
        params["market"] = market
    try:
        r = requests.get(
            "https://api.spotify.com/v1/search",
            params=params,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=10,
        )
    except Exception as e:
        log.error("Eccezione di rete in /v1/search: %s", e)
        return None, -1, str(e)

    if r.status_code != 200:
        body = _short_body(r)
        log.error("/v1/search HTTP %s (market=%s) - body: %s",
                  r.status_code, market, body)
        if r.status_code == 403 and "premium" in body.lower() and "owner" in body.lower():
            _API_BLOCKED_PREMIUM = True
            log.warning("API Spotify bloccata: owner FREE. Useremo i fallback.")
        return None, r.status_code, body

    try:
        items = (r.json().get("tracks") or {}).get("items") or []
    except Exception as e:
        log.error("/v1/search JSON parse error: %s", e)
        return None, r.status_code, _short_body(r)
    return items, r.status_code, None


def _build_query_variants(song: str) -> list:
    """Genera varianti della query da provare in ordine di specificita'
    decrescente. Se la prima non trova risultati validi, prova la seconda,
    ecc. Aiuta con query tipo "ex angelo versione originale di kid yugi":
      1. "ex angelo versione originale di kid yugi"  (originale)
      2. "ex angelo di kid yugi"                     (senza qualificatori versione)
      3. "track:\"ex angelo\" artist:\"kid yugi\""  (Spotify field-filters)
      4. "ex angelo kid yugi"                        (senza connettivi)
      5. "ex angelo"                                 (solo titolo)
    """
    variants = []
    seen = set()

    def _add(v):
        v = (v or "").strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            variants.append(v)

    _add(song)

    cleaned = _strip_version_qualifiers(song)
    _add(cleaned)

    title_guess, artist_guess = _try_split_song_artist(cleaned or song)
    title_clean = _strip_version_qualifiers(title_guess)
    if title_clean and artist_guess:
        # Field filters di Spotify: piu' precisi
        _add(f'track:"{title_clean}" artist:"{artist_guess}"')
        _add(f"{title_clean} {artist_guess}")
    if title_clean:
        _add(title_clean)

    # Se non c'era un separatore esplicito, prova split progressivi
    # ("Alaska Baby Cesare Cremonini" → title="Alaska Baby", artist="Cesare Cremonini").
    if not artist_guess:
        for _t, _a in _progressive_splits(cleaned or song):
            _add(f'track:"{_t}" artist:"{_a}"')
            _add(f"{_t} {_a}")

    return variants


def _search_via_api(song):
    """Cerca via API ufficiale e applica matching intelligente.

    Prova varianti progressive della query per gestire casi come
    "ex angelo versione originale di kid yugi" dove i qualificatori di
    versione confondono la ricerca Spotify.

    FIX v7: se /v1/search restituisce 403 owner-FREE, NON blocchiamo i
    fallback (partner API + HTML). Il flag _API_BLOCKED_PREMIUM viene
    settato solo come informazione diagnostica, non come short-circuit.
    """
    if _API_BLOCKED_PREMIUM:
        return None

    token = _get_app_token()
    if not token:
        token = _get_anon_token()
    if not token:
        return None

    variants = _build_query_variants(song)
    best_overall = None
    best_overall_score = -1.0

    for idx, q in enumerate(variants):
        log.info("Search variant %d/%d: %r", idx + 1, len(variants), q)
        items, status, _ = _do_search_request(token, q, market="IT")

        # FIX: se /v1/search e' bloccato per owner FREE non facciamo
        # early-return qui — restituiamo None e lasciamo che il caller
        # (search_track) provi partner API e i fallback HTML.
        if status == 401:
            log.info("Token scaduto (401), refresh e retry...")
            token = _get_app_token(force_refresh=True) or _get_anon_token()
            if token:
                items, status, _ = _do_search_request(token, q, market="IT")

        if (items is None and status in (400, 404)) or (items is not None and len(items) == 0):
            log.info("Retry senza market...")
            items, status, _ = _do_search_request(token, q, market=None)

        if items is None or len(items) == 0:
            anon = _get_anon_token()
            if anon and anon != token and not _API_BLOCKED_PREMIUM:
                log.info("Fallback con token anonimo web player...")
                items, status, _ = _do_search_request(anon, q, market=None)

        if not items:
            continue

        # Score usando la query ORIGINALE (non la variante) per il matching,
        # cosi' non premiamo l'aver perso informazioni.
        t = _pick_best_match(items, song)
        if not t:
            t = items[0]

        # Punteggio "qualita' del match" per decidere se fermarsi qui o
        # provare la prossima variante. Usiamo somiglianza titolo pulito.
        title_guess, _ = _try_split_song_artist(_strip_version_qualifiers(song))
        qt = _normalize(_strip_version_qualifiers(title_guess or song))
        name_norm = _normalize(t.get("name", ""))
        name_clean = _normalize(_strip_version_qualifiers(t.get("name", "")))
        match_quality = max(
            _name_similarity(qt, name_norm),
            _name_similarity(qt, name_clean),
            _token_overlap(qt, name_clean),
        )
        log.info("  → best per variante: %r - %r (quality=%.2f)",
                 t.get("name"),
                 ", ".join(a["name"] for a in t.get("artists", [])),
                 match_quality)

        if match_quality > best_overall_score:
            best_overall_score = match_quality
            best_overall = t

        # Se abbiamo un match molto buono, fermiamoci.
        if match_quality >= 0.85:
            break

    if not best_overall:
        return None
    return _track_dict(best_overall)


# ------------------------------------------------------------------
# Fallback HTML (oEmbed + DDG / Bing / Mojeek / Startpage / Spotify HTML)
# ------------------------------------------------------------------
def _oembed_meta(track_id):
    try:
        r = requests.get(
            "https://open.spotify.com/oembed",
            params={"url": f"https://open.spotify.com/track/{track_id}"},
            headers={"User-Agent": _UA_BROWSER},
            timeout=10,
        )
        if r.status_code != 200:
            return ("", "")
        data = r.json()
        title = (data.get("title") or "").strip()
        if " - " in title:
            name, artist = title.split(" - ", 1)
            return (name.strip(), artist.strip())
        return (title, "")
    except Exception:
        return ("", "")


def _extract_track_id(html):
    """Estrae un track id da HTML/redirect moderni dei motori di ricerca.

    I motori possono restituire:
      - URL Spotify normali o URL-encoded;
      - URI spotify:track:...;
      - redirect /url?q=...;
      - redirect Bing/Yandex con parametro u= in base64/base64url;
      - JSON/HTML con slash o virgolette escaped.
    """
    if not html:
        return None

    candidates = [str(html)]
    # HTML entities / JSON escaping / percent-encoding possono essere annidati.
    try:
        import html as _html
        candidates.append(_html.unescape(str(html)))
    except Exception:
        pass

    for _ in range(3):
        before = len(candidates)
        for value in list(candidates[-before:]):
            for fn in (unquote,):
                try:
                    decoded = fn(value)
                    if decoded and decoded not in candidates:
                        candidates.append(decoded)
                except Exception:
                    pass
        if len(candidates) == before:
            break

    # Prima cerchiamo direttamente URL e URI Spotify.
    for value in candidates:
        m = _TRACK_ID_RE.search(value)
        if m:
            return m.group(1)
        m = _SPOTIFY_URI_RE.search(value)
        if m:
            return m.group(1)

    # Alcuni redirect usano ?u=<base64url>. Proviamo tutti i parametri
    # plausibili presenti nel documento, senza assumere un solo formato.
    for value in candidates:
        for raw in _B64_PARAM_RE.findall(value):
            token = raw
            for _ in range(2):
                try:
                    token = unquote(token)
                except Exception:
                    break
                try:
                    pad = "=" * (-len(token) % 4)
                    decoded = base64.urlsafe_b64decode(token + pad).decode(
                        "utf-8", errors="ignore"
                    )
                except Exception:
                    break
                if not decoded or decoded == token:
                    break
                m = _TRACK_ID_RE.search(decoded)
                if m:
                    return m.group(1)
                m = _SPOTIFY_URI_RE.search(decoded)
                if m:
                    return m.group(1)
                token = decoded

    # Ultimo tentativo: decodifica esplicitamente query-string di eventuali
    # URL presenti nel risultato (Google/Bing/Qwant/Yandex).
    for value in candidates:
        for match in re.finditer(r'https?://[^\\s<>"\']+', value):
            url = match.group(0)
            try:
                qs = parse_qs(urlparse(url).query)
            except Exception:
                continue
            for vals in qs.values():
                for item in vals:
                    m = _TRACK_ID_RE.search(item)
                    if m:
                        return m.group(1)

    return None


def _search_headers():
    # Header volutamente minimi: alcuni motori classificano come bot le
    # combinazioni Sec-CH-UA/Sec-Fetch più "ricche".
    return {
        "User-Agent": _UA_BROWSER,
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
    }


def _search_via_ddg(song):
    q = f'site:open.spotify.com/track "{song}"'
    headers = _search_headers()
    try:
        with requests.Session() as s:
            r = s.post("https://html.duckduckgo.com/html/",
                       data={"q": q}, headers=headers, timeout=12)
            if r.status_code == 200:
                tid = _extract_track_id(r.text)
                if tid:
                    return tid
            r = s.get("https://lite.duckduckgo.com/lite/",
                       params={"q": q}, headers=headers, timeout=12)
            if r.status_code == 200:
                return _extract_track_id(r.text)
    except Exception:
        pass
    return None


def _search_via_bing(song):
    q = f'site:open.spotify.com/track "{song}"'
    try:
        r = requests.get("https://www.bing.com/search", params={"q": q},
                         headers=_search_headers(), timeout=12)
        if r.status_code == 200:
            return _extract_track_id(r.text)
    except Exception:
        pass
    return None


def _search_via_google(song):
    q = f'site:open.spotify.com/track "{song}"'
    try:
        r = requests.get("https://www.google.com/search",
                         params={"q": q, "num": 10},
                         headers=_search_headers(), timeout=12)
        if r.status_code == 200:
            return _extract_track_id(r.text)
    except Exception:
        pass
    return None


def _search_via_qwant(song):
    q = f'site:open.spotify.com/track "{song}"'
    try:
        r = requests.get("https://www.qwant.com/",
                         params={"q": q, "t": "web"},
                         headers=_search_headers(), timeout=12)
        if r.status_code == 200:
            return _extract_track_id(r.text)
    except Exception:
        pass
    return None


def _search_via_yandex(song):
    q = f'site:open.spotify.com/track "{song}"'
    try:
        r = requests.get("https://yandex.com/search/",
                         params={"text": q},
                         headers=_search_headers(), timeout=12)
        if r.status_code == 200:
            return _extract_track_id(r.text)
    except Exception:
        pass
    return None


def _search_via_mojeek(song):
    q = f'site:open.spotify.com/track "{song}"'
    try:
        r = requests.get("https://www.mojeek.com/search", params={"q": q},
                         headers=_search_headers(), timeout=12)
        if r.status_code == 200:
            return _extract_track_id(r.text)
    except Exception:
        pass
    return None


def _search_via_startpage(song):
    q = f'site:open.spotify.com/track "{song}"'
    try:
        r = requests.post("https://www.startpage.com/sp/search",
                          data={"query": q, "cat": "web"},
                          headers=_search_headers(), timeout=12)
        if r.status_code == 200:
            return _extract_track_id(r.text)
    except Exception:
        pass
    return None


def _search_via_brave(song):
    q = f'site:open.spotify.com/track "{song}"'
    try:
        r = requests.get("https://search.brave.com/search", params={"q": q, "source": "web"},
                         headers=_search_headers(), timeout=12)
        if r.status_code == 200:
            return _extract_track_id(r.text)
    except Exception:
        pass
    return None


def _search_via_ecosia(song):
    q = f'site:open.spotify.com/track "{song}"'
    try:
        r = requests.get("https://www.ecosia.org/search", params={"q": q},
                         headers=_search_headers(), timeout=12)
        if r.status_code == 200:
            return _extract_track_id(r.text)
    except Exception:
        pass
    return None


def _search_via_spotify_html(song):
    """Ricerca via HTML pubblico di open.spotify.com/search/<query>.

    Usa la Session persistente autenticata (cookie sp_dc/sp_key raccolti dalla
    landing page + eventuale bearer anon) così i moderni redirect e le
    inclusioni JSON-in-HTML sono raggiungibili anche senza login pieno.
    """
    url = f"https://open.spotify.com/search/{quote_plus(song)}"
    s = _get_anon_session()
    token = _get_anon_token()
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://open.spotify.com/",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = s.get(url, headers=headers, timeout=12)
        if r.status_code == 200:
            return _extract_track_id(r.text)
    except Exception:
        pass
    return None


# ------------------------------------------------------------------
# SEARCH PUBBLICA (cache 5 min)
# ------------------------------------------------------------------
_SEARCH_CACHE = {}
_SEARCH_CACHE_TTL = 300.0


def _cache_get(key):
    entry = _SEARCH_CACHE.get(key)
    if not entry:
        return None
    ts, track = entry
    if (time.time() - ts) > _SEARCH_CACHE_TTL:
        _SEARCH_CACHE.pop(key, None)
        return None
    return track


def _cache_set(key, track):
    if track:
        _SEARCH_CACHE[key] = (time.time(), track)


def search_track(song):
    if not song or not song.strip():
        return None
    song = song.strip()
    key = song.lower()

    cached = _cache_get(key)
    if cached:
        return cached

    t = _search_via_api(song)
    if t:
        _cache_set(key, t)
        return t

    # Partner API GraphQL: funziona anche se /v1/search è bloccato (owner FREE)
    t = _search_via_partner_api(song)
    if t:
        _cache_set(key, t)
        return t

    fallbacks = (
        _search_via_ddg, _search_via_bing, _search_via_google,
        _search_via_qwant, _search_via_yandex, _search_via_mojeek,
        _search_via_startpage, _search_via_brave, _search_via_ecosia,
        _search_via_spotify_html,
    )
    # Prova gli engine HTML anche con varianti della query (senza field-filter)
    variants = [v for v in _build_query_variants(song)
                if 'track:"' not in v and 'artist:"' not in v]
    if not variants:
        variants = [song]

    track_id = None
    for q in variants:
        for fn in fallbacks:
            track_id = fn(q)
            if track_id:
                log.info("Fallback OK con %s (query=%r) → %s",
                         fn.__name__, q, track_id)
                break
        if track_id:
            break
    if not track_id:
        return None

    name, artist = _oembed_meta(track_id)
    track = {
        "uri": f"spotify:track:{track_id}",
        "id": track_id,
        "name": name or song,
        "artist": artist,
        "popularity": 0,
    }
    _cache_set(key, track)
    return track


# ------------------------------------------------------------------
# DIAGNOSE
# ------------------------------------------------------------------
def diagnose(song="Imagine John Lennon"):
    global _API_BLOCKED_PREMIUM
    # diagnose() deve riflettere solo questa esecuzione, non un 403
    # memorizzato da una ricerca precedente nello stesso processo.
    _API_BLOCKED_PREMIUM = False
    out = {
        "has_credentials": has_credentials(),
        "app_token": None,
        "app_token_len": 0,
        "anon_token_len": 0,
        "client_token_len": 0,
        "search_status_it": None,
        "search_status_nomarket": None,
        "api_blocked_premium": False,
        "first_result": None,
        "best_match": None,
        "all_candidates": [],
        "partner_api_result": None,
        "fallback_results": {},
        "fallback_track_resolved": None,
        "errors": [],
    }
    tok = _get_app_token(force_refresh=True)
    items = None
    if tok:
        out["app_token"] = "OK"
        out["app_token_len"] = len(tok)
        items, status, body = _do_search_request(tok, song, market="IT")
        out["search_status_it"] = status
        if items is None:
            out["errors"].append(f"market=IT → HTTP {status}: {body}")
            if not _API_BLOCKED_PREMIUM:
                items, status, body = _do_search_request(tok, song, market=None)
                out["search_status_nomarket"] = status
                if items is None:
                    out["errors"].append(f"no-market → HTTP {status}: {body}")
        if items:
            t = items[0]
            out["first_result"] = {"name": t["name"], "uri": t["uri"],
                                   "artist": ", ".join(a["name"] for a in t["artists"]),
                                   "popularity": t.get("popularity", 0)}
            out["all_candidates"] = [
                {"name": x["name"],
                 "artist": ", ".join(a["name"] for a in x["artists"]),
                 "popularity": x.get("popularity", 0)}
                for x in items[:10]
            ]
            best = _pick_best_match(items, song)
            if best:
                out["best_match"] = {"name": best["name"], "uri": best["uri"],
                                     "artist": ", ".join(a["name"] for a in best["artists"]),
                                     "popularity": best.get("popularity", 0)}
    out["api_blocked_premium"] = _API_BLOCKED_PREMIUM
    anon = _get_anon_token()
    if anon:
        out["anon_token_len"] = len(anon)
    ctok = _get_client_token()
    if ctok:
        out["client_token_len"] = len(ctok)

    # Partner API: prova indipendentemente dal risultato di /v1/search
    try:
        partner = _search_via_partner_api(song)
        if partner:
            out["partner_api_result"] = partner
    except Exception as e:
        out["errors"].append(f"partner_api → {e}")

    engines = [
        ("ddg", _search_via_ddg),
        ("bing", _search_via_bing),
        ("google", _search_via_google),
        ("qwant", _search_via_qwant),
        ("yandex", _search_via_yandex),
        ("mojeek", _search_via_mojeek),
        ("startpage", _search_via_startpage),
        ("brave", _search_via_brave),
        ("ecosia", _search_via_ecosia),
        ("spotify_html", _search_via_spotify_html),
    ]
    fallback_results = {}
    tid = None
    for name, fn in engines:
        r = fn(song)
        fallback_results[name] = r
        if r and not tid:
            tid = r
    out["fallback_results"] = fallback_results

    if tid:
        name, artist = _oembed_meta(tid)
        out["fallback_track_resolved"] = {
            "id": tid, "uri": f"spotify:track:{tid}",
            "name": name or song, "artist": artist,
        }
    return out


# ------------------------------------------------------------------
# SPOTIFY WINDOW HANDLES (Windows only)
# ------------------------------------------------------------------
def _get_spotify_pids():
    pids = []
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", "IMAGENAME eq Spotify.exe", "/FO", "CSV", "/NH"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).decode(errors="ignore")
        for line in out.splitlines():
            if "spotify.exe" in line.lower():
                parts = [p.strip().strip('"') for p in line.split(",")]
                if len(parts) >= 2:
                    try:
                        pids.append(int(parts[1]))
                    except ValueError:
                        pass
    except Exception:
        pass
    return pids


def _find_all_spotify_hwnds(include_invisible=True):
    pids = _get_spotify_pids()
    if not pids:
        return []
    hwnds = []
    user32 = ctypes.windll.user32

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _lparam):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            if include_invisible or user32.IsWindowVisible(hwnd):
                hwnds.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return hwnds


def _ensure_spotify_running():
    if _get_spotify_pids():
        return True
    paths = [
        os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe"),
        "spotify.exe",
    ]
    for sp in paths:
        try:
            subprocess.Popen([sp])
            for _ in range(20):
                time.sleep(0.3)
                if _get_spotify_pids():
                    return True
            return True
        except Exception:
            continue
    return False


def _send_appcommand(cmd):
    # FIX: Spotify usually exposes several hwnds per process (main window +
    # invisible helper windows). Previously we sent the WM_APPCOMMAND to
    # EVERY hwnd AND we did it twice (SendMessageW + PostMessageW). The
    # media commands (next/previous/play/pause) are edge-triggered, so
    # every duplicated post was effectively counted as an additional user
    # click by Spotify — the visible symptom was "skips two tracks
    # instead of one" when saying "next / previous track". We now send
    # the command exactly ONCE and only to the main visible Spotify
    # window (fallback: first hwnd if none is visible).
    hwnds = _find_all_spotify_hwnds()
    if not hwnds:
        return False
    user32 = ctypes.windll.user32
    PostMessageW = user32.PostMessageW
    PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    PostMessageW.restype = wintypes.BOOL

    target_hwnd = None
    try:
        for hwnd in hwnds:
            if user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
                target_hwnd = hwnd
                break
        if target_hwnd is None:
            for hwnd in hwnds:
                if user32.IsWindowVisible(hwnd):
                    target_hwnd = hwnd
                    break
    except Exception:
        target_hwnd = None
    if target_hwnd is None:
        target_hwnd = hwnds[0]

    try:
        PostMessageW(target_hwnd, WM_APPCOMMAND, target_hwnd, cmd << 16)
        return True
    except Exception:
        return False


# ------------------------------------------------------------------
# WINDOW STATE CAPTURE / RESTORE
# ------------------------------------------------------------------
def _capture_window_states():
    user32 = ctypes.windll.user32
    snapshot = {"target": "normal", "foreground": 0}
    try:
        snapshot["foreground"] = int(user32.GetForegroundWindow() or 0)
    except Exception:
        pass

    hwnds = _find_all_spotify_hwnds(include_invisible=True)
    any_visible = False
    any_visible_normal = False
    for hwnd in hwnds:
        try:
            vis = bool(user32.IsWindowVisible(hwnd))
            ico = bool(user32.IsIconic(hwnd))
            if vis:
                any_visible = True
                if not ico:
                    any_visible_normal = True
        except Exception:
            pass

    if not any_visible:
        snapshot["target"] = "hidden"
    elif not any_visible_normal:
        snapshot["target"] = "minimized"
    else:
        snapshot["target"] = "normal"
    return snapshot


def _apply_target_once(target, prev_fg):
    user32 = ctypes.windll.user32
    try:
        hwnds = _find_all_spotify_hwnds(include_invisible=True)
    except Exception:
        hwnds = []
    for hwnd in hwnds:
        try:
            if target == "hidden":
                if user32.IsWindowVisible(hwnd):
                    user32.ShowWindow(hwnd, SW_MINIMIZE)
                    user32.ShowWindow(hwnd, SW_HIDE)
                    user32.ShowWindow(hwnd, SW_HIDE)
            elif target == "minimized":
                if user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
                    user32.ShowWindow(hwnd, SW_MINIMIZE)
        except Exception:
            pass
    if prev_fg:
        try:
            user32.SetForegroundWindow(prev_fg)
        except Exception:
            pass


# ------------------------------------------------------------------
# PLAY
# ------------------------------------------------------------------
def search_and_play(song, track=None):
    """Cerca e fa partire una canzone.

    FIX v6 - parte SEMPRE, anche se ne stava già suonando un'altra.

    Strategia:
      1. Cattura lo stato della finestra Spotify (hidden/min/normal).
      2. Mandiamo APPCOMMAND_MEDIA_PAUSE → mette Spotify in stato DETERMINISTICO
         (pausa se stava suonando, no-op se era già fermo). Dopo questo
         passo siamo sicuri che lo stato è "non in riproduzione".
      3. Apriamo l'URI: Spotify seleziona/carica la traccia. In stato di
         pausa NON parte da solo.
      4. Aspettiamo che la traccia si carichi, poi riapriamo l'URI: questo
         è un trick affidabile per forzare la riproduzione su Spotify
         desktop quando il client ha appena caricato la traccia.
      5. Come garanzia ulteriore mandiamo APPCOMMAND_MEDIA_PLAY: dato che
         siamo partiti da stato "paused", il toggle ci porta a "playing".
      6. Ripristiniamo lo stato della finestra (hidden/min/normal).
    """
    if track is None:
        if not song or not song.strip():
            return False, "Canzone non specificata.", None
        track = search_track(song)
        if not track:
            return False, f"'{song}' non trovato.", None

    was_running = bool(_get_spotify_pids())
    _ensure_spotify_running()
    if not was_running:
        time.sleep(2.0)

    # 1) Cattura stato finestra
    snapshot = _capture_window_states()
    target = snapshot["target"]
    prev_fg = snapshot["foreground"]

    # 2) Stato deterministico: PAUSA. Se stava già suonando, ora è in pausa.
    #    Se non stava suonando, nessun effetto. APPCOMMAND_MEDIA_PAUSE su
    #    Spotify è dedicato (non toggle), quindi è sicuro mandarlo sempre.
    if was_running:
        _send_appcommand(APPCOMMAND_MEDIA_PAUSE)
        time.sleep(0.2)

    # 3) Apri URI → Spotify seleziona/carica la traccia (non parte perché paused)
    try:
        os.startfile(track["uri"])
    except Exception as e:
        return False, f"Errore apertura traccia: {e}", track["uri"]

    # 4) Aspetta che il client carichi, poi riapri (forza play su Spotify)
    time.sleep(1.0)
    try:
        os.startfile(track["uri"])
    except Exception:
        pass

    # 5) Garanzia: invia PLAY. Dato che lo stato di partenza era "paused"
    #    (passo 2), il toggle ci porta SEMPRE a "playing".
    time.sleep(0.6)
    _send_appcommand(APPCOMMAND_MEDIA_PLAY)

    # 6) Ripristina finestra per 3 secondi (Spotify a volte la rimostra)
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if was_running and target != "normal":
            _apply_target_once(target, prev_fg)
        time.sleep(0.2)

    if was_running and target != "normal":
        _apply_target_once(target, prev_fg)

    label = track["name"]
    if track.get("artist"):
        label += f" - {track['artist']}"
    return True, f"▶️ {label}", track["uri"]


# ------------------------------------------------------------------
# CONTROLLI
# ------------------------------------------------------------------
def pause():
    if _send_appcommand(APPCOMMAND_MEDIA_PAUSE):
        return True, "⏸️ Pausa"
    return False, "Errore pausa: Spotify non in esecuzione"


def resume():
    if _send_appcommand(APPCOMMAND_MEDIA_PLAY):
        return True, "▶️ Play"
    return False, "Errore play: Spotify non in esecuzione"


def next_track():
    if _send_appcommand(APPCOMMAND_MEDIA_NEXTTRACK):
        return True, "⏭️ Next"
    return False, "Errore next: Spotify non in esecuzione"


def previous_track():
    """Torna al brano PRECEDENTE su Spotify.

    Spotify Desktop ha un doppio comportamento nativo sul comando
    ``APPCOMMAND_MEDIA_PREVIOUSTRACK``:
      * se il brano è stato riprodotto per meno di ~3 secondi → torna
        effettivamente al brano precedente,
      * altrimenti (caso normale) → riporta il brano corrente all'inizio
        (equivalente a "riproduci di nuovo questo brano").

    Un singolo click non basta quindi per andare davvero indietro:
    l'utente si aspetta che "torna al brano precedente" salti alla
    traccia precedente sempre, indipendentemente dalla posizione nel
    brano corrente. Per ottenerlo in modo deterministico inviamo prima
    un piccolo seek in avanti (~5 s) con ``APPCOMMAND_MEDIA_FASTFORWARD``
    per portarci sicuramente oltre la soglia dei 3 s, poi mandiamo DUE
    volte ``PREVIOUSTRACK``:
      1. il primo click riporta il brano corrente all'inizio (posizione 0),
      2. il secondo click, ora che ci troviamo a ~0 s, salta al brano
         precedente reale.
    """
    # Nudge in avanti per garantire elapsed > 3 s (APPCOMMAND_MEDIA_FASTFORWARD = 49).
    try:
        _send_appcommand(49)
        time.sleep(0.15)
    except Exception:
        pass
    # 1° click: restart del brano corrente
    ok1 = _send_appcommand(APPCOMMAND_MEDIA_PREVIOUSTRACK)
    if not ok1:
        return False, "Errore previous: Spotify non in esecuzione"
    # Piccola pausa: Spotify deve elaborare il primo comando e resettare
    # l'elapsed. Troppo veloce → i due click vengono coalizzati e conta
    # come uno solo. Troppo lento → il secondo click viene interpretato
    # come "restart" invece che "previous".
    time.sleep(0.25)
    # 2° click: ora elapsed ~ 0 s → salta al brano precedente
    _send_appcommand(APPCOMMAND_MEDIA_PREVIOUSTRACK)
    return True, "⏮️ Previous"


def replay_track():
    """Riavvia dall'inizio il brano attualmente in riproduzione.

    Trick: Spotify Desktop non espone un vero comando "seek to zero", ma
    il comando PREVIOUSTRACK ha un doppio comportamento nativo:
        * se il brano è stato riprodotto per meno di ~3 secondi → torna
          al brano precedente,
        * altrimenti → riporta il brano all'inizio (equivalente a
          "riproduci di nuovo questo brano").
    Per ottenere sempre un "replay dall'inizio" (indipendentemente da
    dove ci si trovi nel brano), inviamo prima un piccolo seek in avanti
    con APPCOMMAND_MEDIA_FASTFORWARD (5s) — così ci troviamo sicuramente
    oltre i 3 secondi — e subito dopo un singolo PREVIOUSTRACK, che
    Spotify interpreta come "restart current track".
    """
    # Nudge di ~5 secondi in avanti per portarci oltre la soglia dei 3s
    # (APPCOMMAND_MEDIA_FASTFORWARD = 49). Se falla non fa nulla, nessun
    # danno.
    try:
        _send_appcommand(49)
        time.sleep(0.15)
    except Exception:
        pass
    if _send_appcommand(APPCOMMAND_MEDIA_PREVIOUSTRACK):
        return True, "🔁 Replay"
    return False, "Errore replay: Spotify non in esecuzione"


def get_current_track():
    return None


# ------------------------------------------------------------------
# REPEAT / LOOP
# ------------------------------------------------------------------
# Spotify Desktop non espone un WM_APPCOMMAND per il repeat. La scorciatoia
# nativa Ctrl+R (Windows) cicla fra le tre modalità:
#     OFF  →  CONTEXT (album/playlist)  →  TRACK  →  OFF  → ...
#
# Non possiamo interrogare lo stato corrente del repeat (le API Web
# richiederebbero un OAuth utente), quindi manteniamo un piccolo state
# tracker interno. Ogni chiamata a ``set_repeat_mode()`` calcola quante
# volte deve premere Ctrl+R per raggiungere lo stato richiesto e aggiorna
# il tracker. Il valore iniziale è "off" — se la realtà è diversa, basta
# una singola chiamata a ``set_repeat_mode('off')`` (che nel worst case
# preme Ctrl+R 2 volte e ci lascia in uno stato noto) per riallinearsi.

_REPEAT_STATE = {"mode": "off"}  # 'off' | 'context' | 'track'
_REPEAT_ORDER = ("off", "context", "track")


def _send_ctrl_r_to_spotify():
    """Invia Ctrl+R alla finestra principale di Spotify (toggle repeat).

    Portiamo brevemente Spotify in foreground, simuliamo Ctrl+R con
    ``keybd_event`` (funziona anche con app Chromium come Spotify) e
    ripristiniamo il foreground precedente. Se Spotify non è in
    esecuzione ritorna False.
    """
    if not _get_spotify_pids():
        return False

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    hwnds = _find_all_spotify_hwnds()
    if not hwnds:
        return False

    # Preferisci la main window visibile e non minimizzata.
    target_hwnd = None
    for hwnd in hwnds:
        try:
            if user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
                target_hwnd = hwnd
                break
        except Exception:
            continue
    if target_hwnd is None:
        target_hwnd = hwnds[0]

    # Snapshot per ripristinare lo stato finestra (hidden/min/normal).
    snapshot = _capture_window_states()
    prev_fg = snapshot["foreground"]
    target_state = snapshot["target"]

    # Porta Spotify in primo piano (necessario perché keybd_event manda
    # l'input al foreground). AttachThreadInput aggira le restrizioni
    # di SetForegroundWindow su Win10/11.
    try:
        if user32.IsIconic(target_hwnd):
            user32.ShowWindow(target_hwnd, SW_SHOWNORMAL)
        current_tid = kernel32.GetCurrentThreadId()
        target_tid = user32.GetWindowThreadProcessId(target_hwnd, None)
        try:
            user32.AttachThreadInput(current_tid, target_tid, True)
            user32.BringWindowToTop(target_hwnd)
            user32.SetForegroundWindow(target_hwnd)
        finally:
            try:
                user32.AttachThreadInput(current_tid, target_tid, False)
            except Exception:
                pass
    except Exception:
        pass

    time.sleep(0.12)

    # Ctrl+R
    VK_CONTROL = 0x11
    VK_R = 0x52
    KEYEVENTF_KEYUP = 0x0002
    try:
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(VK_R, 0, 0, 0)
        time.sleep(0.03)
        user32.keybd_event(VK_R, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.02)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    except Exception:
        return False

    time.sleep(0.12)

    # Ripristina finestra e foreground precedente.
    try:
        if target_state != "normal":
            _apply_target_once(target_state, prev_fg)
        elif prev_fg:
            user32.SetForegroundWindow(prev_fg)
    except Exception:
        pass

    return True


def set_repeat_mode(mode: str):
    """Imposta la modalità di repeat di Spotify.

    :param mode: uno fra ``'off'``, ``'context'`` (album/playlist),
                 ``'track'`` (loop del brano corrente).
    :return: ``(ok: bool, message: str)``.
    """
    mode_norm = (mode or "").strip().lower()
    aliases = {
        "off": "off", "none": "off", "disable": "off", "stop": "off",
        "album": "context", "playlist": "context", "context": "context",
        "queue": "context",
        "song": "track", "track": "track", "current": "track", "one": "track",
    }
    target = aliases.get(mode_norm)
    if target is None:
        return False, f"Modalità loop sconosciuta: {mode}"

    if not _get_spotify_pids():
        return False, "Errore loop: Spotify non in esecuzione"

    current = _REPEAT_STATE.get("mode", "off")
    try:
        cur_idx = _REPEAT_ORDER.index(current)
    except ValueError:
        cur_idx = 0
    tgt_idx = _REPEAT_ORDER.index(target)
    presses = (tgt_idx - cur_idx) % len(_REPEAT_ORDER)

    # Safety net for 'loop_off': if the tracker was NEVER updated (fresh
    # start) but Spotify might have been on any state from a previous
    # session, pressing 0 times could leave the user stuck with an
    # unwanted loop. We keep the tracker as source of truth, but when
    # the target is 'off' and the tracker also says 'off' AND the user
    # just requested loop_off explicitly, we do NOT press: this is the
    # correct behaviour (already off from our POV). The user should
    # first set a loop mode explicitly so the tracker becomes accurate.
    #
    # Correct expected behaviour based on tracker state:
    #   tracker='track'   + loop_off -> 1 press   (track   -> off)
    #   tracker='context' + loop_off -> 2 presses (context -> track -> off)
    #   tracker='off'     + loop_off -> 0 presses (no-op)
    #
    # If a stale tracker returns the wrong result the user can issue an
    # explicit 'loop_song' or 'loop_album' first to re-anchor the state.

    if presses == 0:
        return True, f"🔁 Repeat già su '{target}'"

    for _ in range(presses):
        ok = _send_ctrl_r_to_spotify()
        if not ok:
            return False, "Errore loop: Spotify non in esecuzione"
        time.sleep(0.18)

    _REPEAT_STATE["mode"] = target
    labels = {"off": "off", "context": "album", "track": "brano"}
    return True, f"🔁 Repeat: {labels[target]}"


if __name__ == "__main__":
    print("\n🎵 Spotify Control (FREE) - search API + WM_APPCOMMAND\n")
    song = input("Che canzone vuoi? ").strip()
    if song:
        track = search_track(song)
        if track:
            print(f"\n✅ Trovato: {track['name']}"
                  + (f" - {track['artist']}" if track['artist'] else ""))
            print(f"   URI: {track['uri']}\n")
            ok, msg, _ = search_and_play(song, track=track)
            print(msg)
        else:
            print(f"\n❌ '{song}' non trovato.\n")
            print("💡 Esegui: python -c \"import spotify_api,json;print(json.dumps(spotify_api.diagnose(),indent=2))\"")
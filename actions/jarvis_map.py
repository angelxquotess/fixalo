# actions/jarvis_map.py
# MARK XXXIX-OR - JARVIS HUD MAP (PyQt6 In-Window Edition)
#
# CAMBIAMENTI v4 (richiesti):
# - NON apre piu' una finestra Tk separata.
# - Renderizza la mappa DENTRO la stessa finestra JARVIS (ui.py) come overlay,
#   con animazione di transizione stile Jarvis (fade + slide).
# - FIX CPU 100%: nessun loop di animazione Tk (50 ms), nessuna ricostruzione
#   continua di canvas/corners. Usa QPropertyAnimation di PyQt6 e poi resta
#   IDLE finche' l'utente non interagisce.
# - Mentre la mappa e' aperta, l'utente puo' dire:
#     * "jarvis apri chat"           -> mostra l'overlay chat (spostabile)
#     * "jarvis mostrami statistiche" -> mostra il pannello stats di destra
#     * "torna alla schermata iniziale" -> chiude la mappa (fade out)
#
# La comunicazione con la UI avviene tramite i metodi pubblici esposti
# da ui.JarvisUI:
#     ui.show_map(city, geo, weather, wiki, pois)
#     ui.close_map()
#     ui.is_map_open()
#     ui.show_chat_overlay()
#     ui.show_stats_overlay()
#     ui.return_home()

import json
import threading
import urllib.parse
import urllib.request


# ---------------------------------------------------------------
# Cached reference to the JarvisUI instance (set from main.py via
# set_ui_reference).
# ---------------------------------------------------------------
_UI_REF = {"ui": None}


def set_ui_reference(ui) -> None:
    """Salva il riferimento alla UI principale (chiamato da main.py)."""
    _UI_REF["ui"] = ui


def _get_ui():
    return _UI_REF.get("ui")


# ---------------------------------------------------------------
# Public state helpers (compatibili con la vecchia API)
# ---------------------------------------------------------------
def close_jarvis_map() -> bool:
    """Chiude la mappa nella UI (se aperta)."""
    ui = _get_ui()
    if ui is None:
        return False
    try:
        return bool(ui.close_map())
    except Exception as e:
        print(f"[jarvis_map] close error: {e}")
        return False


def is_jarvis_map_open() -> bool:
    ui = _get_ui()
    if ui is None:
        return False
    try:
        return bool(ui.is_map_open())
    except Exception:
        return False


# ---------------------------------------------------------------
# HTTP helper (stdlib only)
# ---------------------------------------------------------------
def _http_get_json(url: str, timeout: float = 6.0):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "MarkXXXIX-OR-JarvisMap/4.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8", errors="replace")
        return json.loads(data)
    except Exception as e:
        print(f"[jarvis_map] HTTP error: {url[:80]}... -> {e}")
        return None


# ---------------------------------------------------------------
# Geocoding (Nominatim)
# ---------------------------------------------------------------
def _geocode(city: str):
    url = (
        "https://nominatim.openstreetmap.org/search?"
        + urllib.parse.urlencode({"q": city, "format": "json", "limit": 1})
    )
    data = _http_get_json(url) or []
    if not data:
        return None
    item = data[0]
    return {
        "lat": float(item["lat"]),
        "lon": float(item["lon"]),
        "display_name": item.get("display_name", city),
    }


def _wiki_summary(title: str, lang: str = "en"):
    enc = urllib.parse.quote(title.replace(" ", "_"))
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{enc}"
    data = _http_get_json(url)
    if not data or data.get("type", "").endswith("not_found"):
        return None
    return {
        "title": data.get("title", title),
        "extract": (data.get("extract") or "").strip(),
    }


def _wiki_pois(lat: float, lon: float, radius_m: int = 10000, limit: int = 10, lang: str = "en"):
    url = (
        f"https://{lang}.wikipedia.org/w/api.php?"
        + urllib.parse.urlencode({
            "action": "query",
            "list": "geosearch",
            "gscoord": f"{lat}|{lon}",
            "gsradius": radius_m,
            "gslimit": limit,
            "format": "json",
        })
    )
    data = _http_get_json(url) or {}
    items = ((data.get("query") or {}).get("geosearch")) or []
    return [
        {"title": it.get("title"), "lat": it.get("lat"), "lon": it.get("lon")}
        for it in items
    ]


def _weather(lat: float, lon: float):
    url = (
        "https://api.open-meteo.com/v1/forecast?"
        + urllib.parse.urlencode({
            "latitude": lat,
            "longitude": lon,
            "current_weather": "true",
        })
    )
    data = _http_get_json(url) or {}
    cw = data.get("current_weather") or {}
    if not cw:
        return None
    return {
        "temperature": cw.get("temperature"),
        "windspeed":   cw.get("windspeed"),
        "weathercode": cw.get("weathercode"),
    }


def _short_extract(text: str, max_chars: int = 280) -> str:
    if not text:
        return "No data available for this target."
    text = text.replace("\n", " ").strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(".", 1)[0]
    return cut + "..."


# ---------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------
def jarvis_map(parameters=None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    city = (params.get("city") or params.get("location") or "").strip()
    if not city:
        return "Sir, you must tell me which city to display on the map."

    ui = _get_ui()
    if ui is None and player is not None:
        # fallback: la UI puo' anche essere passata come `player`
        ui = player
        _UI_REF["ui"] = ui

    def log(m):
        print(f"[jarvis_map] {m}")
        if player:
            try:
                player.write_log(f"[map] {m}")
            except Exception:
                pass

    log(f"target acquired: {city}")
    geo = _geocode(city)
    if not geo:
        return f"Sir, I cannot locate '{city}' on the map."

    weather = _weather(geo["lat"], geo["lon"])
    wiki    = _wiki_summary(city, lang="en") or _wiki_summary(city, lang="it")
    pois    = _wiki_pois(geo["lat"], geo["lon"], radius_m=10000, limit=10, lang="en")

    # Mostra la mappa DENTRO la UI principale (nessuna nuova finestra).
    # Lo facciamo in background thread perche' lo data-fetch e' gia'
    # avvenuto, ma il setup UI deve girare sul main thread Qt: la UI
    # gestisce internamente l'invoke via signal.
    if ui is None:
        log("UI non disponibile: la mappa non puo' essere mostrata.")
        return f"UI not ready, cannot display {city}."

    def _show():
        try:
            ui.show_map(city, geo, weather, wiki, pois)
        except Exception as e:
            log(f"show_map error: {e}")

    threading.Thread(target=_show, name="JarvisMapShow", daemon=True).start()

    pieces = [f"Displaying {city} on the tactical map, sir."]
    if weather and weather.get("temperature") is not None:
        pieces.append(f"Current temperature is {weather['temperature']} degrees.")
    if wiki and wiki.get("extract"):
        pieces.append(_short_extract(wiki["extract"], 200))
    return " ".join(pieces)

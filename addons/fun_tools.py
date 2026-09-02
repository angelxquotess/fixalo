"""addons/fun_tools.py — utility varie: password, calc, conversioni, orologi,
meteo esteso (open-meteo, senza chiave), citazioni, barzellette, trivia."""
from __future__ import annotations

import json
import random
import secrets
import string
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

# --------------------------------------------------------------- password
def gen_password(length: int = 16, symbols: bool = True) -> str:
    alphabet = string.ascii_letters + string.digits
    if symbols:
        alphabet += "!@#$%^&*()-_=+"
    return "".join(secrets.choice(alphabet) for _ in range(int(length)))

def gen_passphrase(words: int = 4) -> str:
    wordlist = ("sole luna mare vento terra fuoco acqua luce ombra stella "
                "nube fiume monte valle bosco fiore roccia onda neve gelo "
                "caldo freddo nord sud est ovest alba tramonto notte giorno").split()
    return "-".join(secrets.choice(wordlist) for _ in range(int(words)))

# -------------------------------------------------------------- calcolatrice
_ALLOWED = set("0123456789+-*/().%")

def calc(expr: str) -> str:
    expr = (expr or "").strip()
    if not expr or any(not c.isspace() and c not in _ALLOWED for c in expr):
        return "Espressione non valida."
    try:
        return str(eval(expr, {"__builtins__": {}}, {}))
    except Exception as e:
        return f"Errore: {e}"

# -------------------------------------------------------------- conversioni
def convert(value: float, from_unit: str, to_unit: str) -> str:
    u = {
        # lunghezza -> metri
        "mm": 0.001, "cm": 0.01, "m": 1.0, "km": 1000.0,
        "in": 0.0254, "ft": 0.3048, "mi": 1609.34,
    }
    w = {"g": 1.0, "kg": 1000.0, "lb": 453.592, "oz": 28.3495, "t": 1e6}
    f, t = from_unit.lower(), to_unit.lower()
    try:
        v = float(value)
        if f in u and t in u:
            return f"{v} {f} = {v * u[f] / u[t]:.4f} {t}"
        if f in w and t in w:
            return f"{v} {f} = {v * w[f] / w[t]:.4f} {t}"
        if f == "c" and t == "f":
            return f"{v} C = {v * 9/5 + 32:.1f} F"
        if f == "f" and t == "c":
            return f"{v} F = {(v - 32) * 5/9:.1f} C"
        return "Unita' non supportata."
    except Exception as e:
        return f"Errore: {e}"

# ------------------------------------------------------------- orologio mondo
def world_clock(cities: list[str] | None = None) -> dict:
    cities = cities or ["Europe/Rome", "America/New_York", "Asia/Tokyo",
                        "Australia/Sydney", "Europe/London"]
    out = {}
    for tz in cities:
        try:
            out[tz] = datetime.now(ZoneInfo(tz)).strftime("%H:%M")
        except Exception:
            out[tz] = "?"
    return out

# --------------------------------------------- meteo esteso (no API key)
def weather_now(city: str = "Roma") -> dict:
    try:
        g = json.loads(urllib.request.urlopen(
            f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1",
            timeout=8).read())
        loc = g["results"][0]
        w = json.loads(urllib.request.urlopen(
            "https://api.open-meteo.com/v1/forecast?"
            f"latitude={loc['latitude']}&longitude={loc['longitude']}"
            "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
            "precipitation,weather_code,wind_speed_10m",
            timeout=8).read())["current"]
        return {"city": loc["name"], "temp_c": w["temperature_2m"],
                "feels_c": w["apparent_temperature"],
                "humidity": w["relative_humidity_2m"],
                "wind_kmh": w["wind_speed_10m"],
                "precip_mm": w["precipitation"]}
    except Exception as e:
        return {"error": str(e)}

def air_quality(city: str = "Roma") -> dict:
    try:
        g = json.loads(urllib.request.urlopen(
            f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1",
            timeout=8).read())
        loc = g["results"][0]
        a = json.loads(urllib.request.urlopen(
            "https://air-quality-api.open-meteo.com/v1/air-quality?"
            f"latitude={loc['latitude']}&longitude={loc['longitude']}"
            "&current=european_aqi,pm2_5,pm10",
            timeout=8).read())["current"]
        return {"city": loc["name"], "european_aqi": a["european_aqi"],
                "pm2_5": a["pm2_5"], "pm10": a["pm10"]}
    except Exception as e:
        return {"error": str(e)}

# ------------------------------------------------------------- citazioni
_QUOTES = [
    "Il modo migliore per predire il futuro e' inventarlo. — Alan Kay",
    "Prima risolvi il problema, poi scrivi il codice. — John Johnson",
    "La semplicita' e' la massima sofisticazione. — Leonardo da Vinci",
    "Il software e' come il sesso: e' meglio quando e' gratis. — Linus Torvalds",
    "Talk is cheap. Show me the code. — Linus Torvalds",
    "Non e' un bug, e' una feature non documentata.",
    "Funziona sulla mia macchina.",
    "Ci sono solo due industrie che chiamano i clienti 'utenti'. — Edward Tufte",
]

def quote() -> str:
    return random.choice(_QUOTES)

# ------------------------------------------------------------ barzellette
_JOKES = [
    "Perche' i programmatori confondono Halloween e Natale? Perche' OCT 31 == DEC 25.",
    "Un SQL entra in un bar, vede due tavoli e chiede: 'Posso fare un JOIN?'",
    "Ci sono 10 tipi di persone: chi capisce il binario e chi no.",
    "Perche' il programmatore e' sempre al freddo? Perche' lascia sempre le Windows aperte.",
    "Come si chiama un developer che non commenta il codice? Un archeologo tra 6 mesi.",
    "Il debug e' come essere il detective di un film giallo in cui sei anche l'assassino.",
]

def joke() -> str:
    return random.choice(_JOKES)

# ----------------------------------------------------------------- trivia
_TRIVIA = [
    ("Quanti bit ci sono in un byte?", "8"),
    ("In che anno e' nato Python?", "1991"),
    ("Chi ha creato Linux?", "Linus Torvalds"),
    ("Cosa significa HTTP?", "HyperText Transfer Protocol"),
    ("Quale pianeta e' il piu' grande del sistema solare?", "Giove"),
]

def trivia() -> dict:
    q, a = random.choice(_TRIVIA)
    return {"question": q, "answer": a}

# --------------------------------------------------------------- testo
def text_stats(text: str) -> dict:
    words = text.split()
    return {"chars": len(text), "words": len(words),
            "sentences": text.count(".") + text.count("!") + text.count("?")}

def text_transform(text: str, mode: str) -> str:
    modes = {
        "upper": str.upper, "lower": str.lower, "title": str.title,
        "reverse": lambda s: s[::-1],
        "snake": lambda s: s.lower().replace(" ", "_"),
    }
    fn = modes.get(mode)
    return fn(text) if fn else f"Modalita' '{mode}' non valida."

# --------------------------------------------------------- dadi e moneta
def roll_dice(sides: int = 6, count: int = 1) -> list[int]:
    return [random.randint(1, int(sides)) for _ in range(int(count))]

def coin_flip() -> str:
    return random.choice(["Testa", "Croce"])

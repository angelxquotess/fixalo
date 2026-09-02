"""addons/network_tools.py — rete: IP, speed test, porte, RSS, DNS."""
from __future__ import annotations

import socket
import time
import urllib.request
import xml.etree.ElementTree as ET

from .core import run_silent

# ------------------------------------------------------------------- IP
def public_ip() -> str:
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=6) as r:
            return r.read().decode().strip()
    except Exception as e:
        return f"Errore: {e}"

def local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def ip_details() -> dict:
    import json
    try:
        with urllib.request.urlopen("https://ipinfo.io/json", timeout=6) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}

# ------------------------------------------------------------- speed test
def speed_test(url: str = "https://speed.cloudflare.com/__down?bytes=10000000",
               ) -> dict:
    """Download test semplice (10MB) — niente dipendenze esterne."""
    try:
        t0 = time.time()
        with urllib.request.urlopen(url, timeout=30) as r:
            data = r.read()
        dt = time.time() - t0
        mbps = (len(data) * 8) / (dt * 1_000_000)
        return {"downloaded_mb": round(len(data) / 1e6, 1),
                "seconds": round(dt, 2),
                "download_mbps": round(mbps, 1)}
    except Exception as e:
        return {"error": str(e)}

def ping(host: str = "8.8.8.8", count: int = 4) -> str:
    import sys
    flag = "-n" if sys.platform.startswith("win") else "-c"
    rc, out = run_silent(["ping", flag, str(count), host], timeout=15)
    return out.strip().splitlines()[-1] if out.strip() else f"ping fallito (rc={rc})"

# --------------------------------------------------------------- port scan
def scan_ports(host: str, ports=None, timeout: float = 0.5) -> list[int]:
    ports = ports or [21, 22, 25, 53, 80, 110, 143, 443, 445,
                      3306, 3389, 5900, 8080, 8443]
    open_ports = []
    for port in ports:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                open_ports.append(port)
        except Exception:
            pass
    return open_ports

# ------------------------------------------------------------------- RSS
def rss_headlines(feed_url: str, n: int = 5) -> list[dict]:
    try:
        with urllib.request.urlopen(feed_url, timeout=10) as r:
            root = ET.fromstring(r.read())
        items = root.findall(".//item") or root.findall(
            ".//{http://www.w3.org/2005/Atom}entry")
        out = []
        for it in items[:n]:
            title = it.findtext("title") or it.findtext(
                "{http://www.w3.org/2005/Atom}title") or ""
            out.append({"title": title.strip()})
        return out
    except Exception as e:
        return [{"error": str(e)}]

# ------------------------------------------------------------------- DNS
def flush_dns() -> str:
    import sys
    if sys.platform.startswith("win"):
        rc, out = run_silent(["ipconfig", "/flushdns"])
    else:
        rc, out = run_silent(["resolvectl", "flush-caches"])
    return "DNS cache svuotata." if rc == 0 else f"Errore: {out[:200]}"

def dns_lookup(host: str) -> list[str]:
    try:
        return sorted({ai[4][0] for ai in socket.getaddrinfo(host, None)})
    except Exception as e:
        return [f"Errore: {e}"]

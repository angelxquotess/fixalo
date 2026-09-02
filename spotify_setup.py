"""Spotify Setup - Configurazione credenziali + verifica ricerca.

[FIX v4 - 2026-01]
- Mostra il nuovo campo `best_match` dal diagnose(): cosi vedi subito
  se la canzone selezionata e' quella giusta (matching basato su
  somiglianza nome + popolarita').
- Mantiene il riconoscimento dell'errore "Active premium subscription
  required for the owner of the app" → fallback HTML.

Premium NON richiesto per FAR PARTIRE le canzoni nel client desktop.
"""
import json
from pathlib import Path

CREDS_FILE = Path(__file__).resolve().parent / "spotify_credentials.txt"


def _print_dashboard_guide():
    print("\n📘 Come ottenere client_id e client_secret (2 minuti, GRATIS):")
    print("   1) Vai su https://developer.spotify.com/dashboard")
    print("   2) Login con il tuo account Spotify (anche FREE)")
    print("   3) Click 'Create app'")
    print("   4) App name: qualsiasi (es. 'jarvis-local')")
    print("      App description: qualsiasi")
    print("      Redirect URI: http://localhost:8888 (non viene usato)")
    print("      APIs: spunta 'Web API'")
    print("   5) Save → poi 'Settings' → copia 'Client ID' e 'Client secret'")
    print()


def _save_credentials(cid: str, csec: str):
    CREDS_FILE.write_text(
        f"# Credenziali Spotify (Client Credentials Flow)\n"
        f"# Non condividere questo file pubblicamente.\n"
        f"client_id={cid}\n"
        f"client_secret={csec}\n",
        encoding="utf-8",
    )


def _credentials_exist():
    if not CREDS_FILE.exists():
        return False
    try:
        content = CREDS_FILE.read_text(encoding="utf-8")
    except Exception:
        return False
    has_id = "client_id=" in content and not content.split("client_id=", 1)[1].lstrip().startswith(("\n", "#"))
    has_sec = "client_secret=" in content and not content.split("client_secret=", 1)[1].lstrip().startswith(("\n", "#"))
    return has_id and has_sec


def configure_credentials(force: bool = False):
    if _credentials_exist() and not force:
        print(f"✅ Credenziali già presenti in: {CREDS_FILE.name}")
        choice = input("   Vuoi sostituirle? [s/N]: ").strip().lower()
        if choice not in ("s", "si", "sì", "y", "yes"):
            return True

    _print_dashboard_guide()
    cid = input("👉 Incolla Client ID: ").strip()
    csec = input("👉 Incolla Client Secret: ").strip()
    if not cid or not csec:
        print("❌ Credenziali vuote, annullato.")
        return False
    _save_credentials(cid, csec)
    print(f"✅ Salvate in: {CREDS_FILE}")
    return True


def verify():
    print("\n" + "=" * 60)
    print("SPOTIFY CONTROL - VERIFICA SETUP (FREE)")
    print("=" * 60 + "\n")

    try:
        import requests  # noqa: F401
        print("✅ requests installato")
    except ImportError:
        print("❌ `requests` NON installato — installa con: pip install requests\n")
        return False

    try:
        import spotify_api
    except Exception as e:
        print(f"❌ Impossibile importare spotify_api: {e}\n")
        return False

    print("\n🔄 Verifica credenziali Spotify (Client Credentials Flow)...")
    if not spotify_api.has_credentials():
        print("   ⚠️ Nessuna credenziale trovata.")
        print("   (Con account FREE le credenziali NON sbloccano la Web API,")
        print("    servono solo se in futuro passi a Premium. Userò i fallback HTML.)")
    else:
        print("✅ Credenziali presenti.")

    print("\n🔄 Diagnose completa (API + matching + fallback HTML)...")
    diag = spotify_api.diagnose("Diversi Shiva")
    print(json.dumps(diag, indent=2, ensure_ascii=False))

    api_works = diag.get("first_result") is not None
    best = diag.get("best_match")
    fallback_works = diag.get("fallback_track_resolved") is not None
    owner_free = diag.get("api_blocked_premium", False)

    print("\n" + "-" * 60)
    if api_works:
        print("✅ Web API Spotify OK")
        print(f"   1° risultato Spotify: {diag['first_result']['name']} - {diag['first_result']['artist']} "
              f"(pop={diag['first_result']['popularity']})")
        if best:
            print(f"   ⭐ BEST MATCH (matching intelligente): {best['name']} - {best['artist']} "
                  f"(pop={best['popularity']})")
    elif owner_free:
        print("ℹ️ Web API BLOCCATA dal 2025 (owner FREE su Dashboard).")
        print("   Useremo i fallback HTML — funzionano comunque.")
    else:
        print("⚠️ Web API non funziona (vedi 'errors' sopra).")

    if fallback_works:
        fb = diag["fallback_track_resolved"]
        print(f"\n✅ Fallback HTML OK → {fb['name']}"
              + (f" - {fb['artist']}" if fb['artist'] else ""))
        for name, tid in (diag.get("fallback_results") or {}).items():
            if tid:
                print(f"   Origine: {name}")
                break
    elif not api_works:
        print("\n❌ Anche i fallback HTML hanno fallito.")
        return False

    print("\n🔄 Test artista underground italiano ('Kid Yugi')...")
    track2 = spotify_api.search_track("Kid Yugi")
    if track2:
        label = track2["name"] + (f" - {track2['artist']}" if track2.get("artist") else "")
        print(f"   ✅ Trovato: {label}")
    else:
        print("   ⚠️ Non trovato.")

    print("\n" + "=" * 60)
    print("🎉 SETUP OK!")
    print("=" * 60)
    if owner_free:
        print("📌 Modalità: FREE (Web API disabilitata, fallback HTML attivo)")
    print("✅ Comando manuale: python spotify_api.py")
    print("✅ Integrazione Jarvis: import spotify_api → spotify_api.search_and_play('canzone')")
    print()
    return True


if __name__ == "__main__":
    verify()
